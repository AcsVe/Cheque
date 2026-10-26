"""Local SQLite database (one file in the data folder). Schema changes are numbered migrations applied at start-up;
nothing is ever dropped. All money is stored as text (Decimal) to keep the fils exact."""
import json
import os
import shutil
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .templates import default_template, upgrade_saved

MIGRATIONS = [
    # 1 — initial schema
    """
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, name_en TEXT, is_active INTEGER NOT NULL DEFAULT 1,
        template TEXT NOT NULL, background TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_id INTEGER NOT NULL REFERENCES banks(id),
        name TEXT NOT NULL, number TEXT, currency TEXT NOT NULL DEFAULT 'JOD',
        next_no INTEGER NOT NULL DEFAULT 1, last_no INTEGER, is_active INTEGER NOT NULL DEFAULT 1,
        notes TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS payees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, name_en TEXT, phone TEXT, notes TEXT,
        is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cheques (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        cheque_no INTEGER NOT NULL, cheque_date TEXT NOT NULL,
        payee TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'JOD',
        words TEXT, crossing TEXT NOT NULL DEFAULT 'none', memo TEXT,
        status TEXT NOT NULL DEFAULT 'saved', print_count INTEGER NOT NULL DEFAULT 0, printed_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE (account_id, cheque_no));
    CREATE INDEX IF NOT EXISTS ix_cheques_date ON cheques (cheque_date);
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL, details TEXT);
    """,
]

STATUSES = {'saved': ('محفوظ', 'Saved'), 'printed': ('مطبوع', 'Printed'), 'cancelled': ('ملغى', 'Cancelled')}
CROSSINGS = {'none': ('بدون تسطير', 'No crossing'), 'first': ('المستفيد الأول', 'First beneficiary'),
             'account': ('بالحساب', 'Account only'), 'both': ('المستفيد الأول + بالحساب', 'First beneficiary + account')}


def now():
    return datetime.now().isoformat(timespec='seconds')


def to_decimal(value):
    try:
        d = Decimal(str(value).replace(',', '').replace('٫', '.').strip()
                    .translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')))
    except (InvalidOperation, AttributeError):
        return None
    return d if d.is_finite() else None


class Database:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA foreign_keys = ON')
        self.con.execute('PRAGMA journal_mode = WAL')
        self._migrate()

    # ── schema ───────────────────────────────────────────────────────
    def _migrate(self):
        self.con.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        v = int(self.get('schema_version', '0'))
        for i, sql in enumerate(MIGRATIONS, 1):
            if i > v:
                self.con.executescript(sql)
                self.set('schema_version', str(i))
        if not self.con.execute('SELECT 1 FROM banks LIMIT 1').fetchone():
            self.con.execute('INSERT INTO banks (name, name_en, template, created_at) VALUES (?, ?, ?, ?)',
                             ('قالب عام', 'Generic', json.dumps(default_template(), ensure_ascii=False), now()))
        self.con.commit()

    def close(self):
        self.con.close()

    # ── settings ─────────────────────────────────────────────────────
    def get(self, key, default=None):
        row = self.con.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        self.con.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                         (key, None if value is None else str(value)))
        self.con.commit()

    def audit(self, action, **details):
        self.con.execute('INSERT INTO audit (at, action, details) VALUES (?, ?, ?)',
                         (now(), action, json.dumps(details, ensure_ascii=False, default=str)))

    # ── banks / templates ────────────────────────────────────────────
    def banks(self, active_only=False):
        q = 'SELECT * FROM banks' + (' WHERE is_active = 1' if active_only else '') + ' ORDER BY name'
        return [dict(r) for r in self.con.execute(q)]

    def bank(self, bank_id):
        r = self.con.execute('SELECT * FROM banks WHERE id = ?', (bank_id,)).fetchone()
        return dict(r) if r else None

    def template(self, bank_id):
        b = self.bank(bank_id)
        base = default_template()
        if b:
            try:
                t = upgrade_saved(json.loads(b['template']))
                base.update({k: v for k, v in t.items() if k != 'fields'})
                for k, f in (t.get('fields') or {}).items():
                    base['fields'].setdefault(k, {}).update(f)
            except ValueError:
                pass
        return base

    def save_bank(self, data, bank_id=None):
        tpl = json.dumps(data.get('template') or default_template(), ensure_ascii=False)
        if bank_id:
            self.con.execute('UPDATE banks SET name=?, name_en=?, is_active=?, template=?, background=? WHERE id=?',
                             (data['name'], data.get('name_en'), int(data.get('is_active', 1)), tpl,
                              data.get('background'), bank_id))
        else:
            bank_id = self.con.execute('INSERT INTO banks (name, name_en, is_active, template, background, created_at) '
                                       'VALUES (?, ?, ?, ?, ?, ?)',
                                       (data['name'], data.get('name_en'), int(data.get('is_active', 1)), tpl,
                                        data.get('background'), now())).lastrowid
        self.audit('bank.saved', id=bank_id, name=data['name'])
        self.con.commit()
        return bank_id

    def bank_in_use(self, bank_id):
        return self.con.execute('SELECT COUNT(*) FROM accounts WHERE bank_id = ?', (bank_id,)).fetchone()[0]

    # ── accounts ─────────────────────────────────────────────────────
    def accounts(self, active_only=False):
        q = ('SELECT a.*, b.name AS bank_name FROM accounts a JOIN banks b ON b.id = a.bank_id'
             + (' WHERE a.is_active = 1' if active_only else '') + ' ORDER BY b.name, a.name')
        return [dict(r) for r in self.con.execute(q)]

    def account(self, account_id):
        r = self.con.execute('SELECT a.*, b.name AS bank_name FROM accounts a JOIN banks b ON b.id = a.bank_id '
                             'WHERE a.id = ?', (account_id,)).fetchone()
        return dict(r) if r else None

    def save_account(self, data, account_id=None):
        vals = (int(data['bank_id']), data['name'], data.get('number'), data.get('currency') or 'JOD',
                int(data.get('next_no') or 1), (int(data['last_no']) if data.get('last_no') else None),
                int(data.get('is_active', 1)), data.get('notes'))
        if account_id:
            self.con.execute('UPDATE accounts SET bank_id=?, name=?, number=?, currency=?, next_no=?, last_no=?, '
                             'is_active=?, notes=? WHERE id=?', vals + (account_id,))
        else:
            account_id = self.con.execute('INSERT INTO accounts (bank_id, name, number, currency, next_no, last_no, '
                                          'is_active, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                          vals + (now(),)).lastrowid
        self.audit('account.saved', id=account_id, name=data['name'])
        self.con.commit()
        return account_id

    def account_in_use(self, account_id):
        return self.con.execute('SELECT COUNT(*) FROM cheques WHERE account_id = ?', (account_id,)).fetchone()[0]

    def next_cheque_no(self, account_id):
        a = self.account(account_id)
        if not a:
            return 1
        used = {r[0] for r in self.con.execute('SELECT cheque_no FROM cheques WHERE account_id = ?', (account_id,))}
        n = int(a['next_no'] or 1)
        while n in used:
            n += 1
        return n

    # ── payees ───────────────────────────────────────────────────────
    def payees(self, active_only=False):
        q = ('SELECT p.*, (SELECT COUNT(*) FROM cheques c WHERE c.payee = p.name) AS cheques FROM payees p'
             + (' WHERE p.is_active = 1' if active_only else '') + ' ORDER BY p.name')
        return [dict(r) for r in self.con.execute(q)]

    def save_payee(self, data, payee_id=None):
        name = (data.get('name') or '').strip()
        if not name:
            raise ValueError('name')
        vals = (name, data.get('name_en'), data.get('phone'), data.get('notes'), int(data.get('is_active', 1)))
        if payee_id:
            self.con.execute('UPDATE payees SET name=?, name_en=?, phone=?, notes=?, is_active=? WHERE id=?',
                             vals + (payee_id,))
        else:
            payee_id = self.con.execute('INSERT INTO payees (name, name_en, phone, notes, is_active, created_at) '
                                        'VALUES (?, ?, ?, ?, ?, ?)', vals + (now(),)).lastrowid
        self.con.commit()
        return payee_id

    def ensure_payee(self, name):
        name = (name or '').strip()
        if name and not self.con.execute('SELECT 1 FROM payees WHERE name = ?', (name,)).fetchone():
            self.con.execute('INSERT INTO payees (name, created_at) VALUES (?, ?)', (name, now()))

    # ── cheques ──────────────────────────────────────────────────────
    def cheques(self, where='', params=()):
        q = ('SELECT c.*, a.name AS account_name, a.number AS account_number, b.name AS bank_name, a.bank_id '
             'FROM cheques c JOIN accounts a ON a.id = c.account_id JOIN banks b ON b.id = a.bank_id '
             + (f'WHERE {where} ' if where else '') + 'ORDER BY c.cheque_date DESC, c.id DESC')
        return [dict(r) for r in self.con.execute(q, params)]

    def cheque(self, cheque_id):
        rows = self.cheques('c.id = ?', (cheque_id,))
        return rows[0] if rows else None

    def find_cheque(self, account_id, cheque_no):
        rows = self.cheques('c.account_id = ? AND c.cheque_no = ?', (account_id, cheque_no))
        return rows[0] if rows else None

    def save_cheque(self, data, cheque_id=None):
        """data: account_id, cheque_no, cheque_date (YYYY-MM-DD), payee, amount, words, crossing, memo.
        → id. Raises ValueError(code) for invalid input."""
        amount = to_decimal(data.get('amount'))
        if amount is None or amount <= 0:
            raise ValueError('amount')
        payee = (data.get('payee') or '').strip()
        if not payee:
            raise ValueError('payee')
        acc = self.account(int(data['account_id']))
        if not acc:
            raise ValueError('account')
        no = int(data['cheque_no'])
        if acc.get('last_no') and no > int(acc['last_no']):
            raise ValueError('beyond_book')
        dup = self.find_cheque(acc['id'], no)
        if dup and dup['id'] != cheque_id:
            raise ValueError('duplicate')
        if cheque_id:
            cur = self.cheque(cheque_id)
            if cur and cur['status'] == 'cancelled':
                raise ValueError('cancelled')
        vals = (acc['id'], no, data['cheque_date'], payee, format(amount, 'f'), acc['currency'],
                data.get('words'), data.get('crossing') or 'none', data.get('memo'))
        if cheque_id:
            self.con.execute('UPDATE cheques SET account_id=?, cheque_no=?, cheque_date=?, payee=?, amount=?, currency=?, '
                             'words=?, crossing=?, memo=?, updated_at=? WHERE id=?', vals + (now(), cheque_id))
            self.audit('cheque.updated', id=cheque_id, no=no)
        else:
            cheque_id = self.con.execute('INSERT INTO cheques (account_id, cheque_no, cheque_date, payee, amount, currency, '
                                         'words, crossing, memo, status, created_at, updated_at) '
                                         'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                         vals + ('saved', now(), now())).lastrowid
            self.audit('cheque.saved', id=cheque_id, no=no, amount=format(amount, 'f'), payee=payee)
        if no >= int(acc['next_no'] or 1):
            self.con.execute('UPDATE accounts SET next_no = ? WHERE id = ?', (no + 1, acc['id']))
        self.ensure_payee(payee)
        self.con.commit()
        return cheque_id

    def mark_printed(self, cheque_id):
        self.con.execute("UPDATE cheques SET status = CASE WHEN status = 'cancelled' THEN status ELSE 'printed' END, "
                         "print_count = print_count + 1, printed_at = ?, updated_at = ? WHERE id = ?",
                         (now(), now(), cheque_id))
        self.audit('cheque.printed', id=cheque_id)
        self.con.commit()

    def set_status(self, ids, status):
        n = 0
        for i in ids:
            n += self.con.execute('UPDATE cheques SET status = ?, updated_at = ? WHERE id = ?', (status, now(), i)).rowcount
            self.audit(f'cheque.{status}', id=i)
        self.con.commit()
        return n

    def delete_cheques(self, ids):
        """Only cheques never printed can be deleted; printed ones are cancelled instead (the number stays used)."""
        done, kept = 0, []
        for i in ids:
            c = self.cheque(i)
            if not c:
                continue
            if c['print_count'] or c['status'] == 'printed':
                kept.append(c['cheque_no'])
                continue
            self.con.execute('DELETE FROM cheques WHERE id = ?', (i,))
            self.audit('cheque.deleted', id=i, no=c['cheque_no'])
            done += 1
        self.con.commit()
        return done, kept

    def delete_rows(self, table, ids, guard=None):
        """Generic delete for payees/accounts/banks; ``guard(id)`` returns a reason to keep a row."""
        done, kept = 0, []
        for i in ids:
            why = guard(i) if guard else None
            if why:
                kept.append(why)
                continue
            self.con.execute(f'DELETE FROM {table} WHERE id = ?', (i,))
            done += 1
        self.audit(f'{table}.deleted', count=done)
        self.con.commit()
        return done, kept

    def set_active(self, table, ids, active):
        for i in ids:
            self.con.execute(f'UPDATE {table} SET is_active = ? WHERE id = ?', (1 if active else 0, i))
        self.con.commit()
        return len(ids)

    # ── backup ───────────────────────────────────────────────────────
    def backup(self, folder, keep=30):
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, f'cheques-{datetime.now():%Y%m%d-%H%M%S}.db')
        dst = sqlite3.connect(target)
        with dst:
            self.con.backup(dst)
        dst.close()
        files = sorted(f for f in os.listdir(folder) if f.startswith('cheques-') and f.endswith('.db'))
        for old in files[:-keep]:
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
        return target

    def restore(self, source):
        """Replace the data with a backup file (the current data is backed up first)."""
        test = sqlite3.connect(source)
        try:
            if not test.execute("SELECT name FROM sqlite_master WHERE name = 'cheques'").fetchone():
                raise ValueError('not_a_backup')
        finally:
            test.close()
        safety = self.backup(os.path.join(os.path.dirname(self.path), 'backups'))
        self.con.close()
        for ext in ('-wal', '-shm'):
            if os.path.exists(self.path + ext):
                os.remove(self.path + ext)
        shutil.copyfile(source, self.path)
        self.__init__(self.path)
        return safety
