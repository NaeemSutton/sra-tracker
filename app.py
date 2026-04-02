from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'sra-tracker-secret-2024'
DB = 'sra_tracker.db'

MANAGER_PASSWORD = 'manager123'
ANALYSTS = ['Naeem', 'Analyst 2', 'Analyst 3', 'Analyst 4']

# Docs per tier — MDS2 added dynamically if medical device
TIER_DOCS = {
    'A': [
        'Vendor Technical Questionnaire',
        'SOC2 Type II or HITRUST Full Report',
        'HIPAA Risk Assessment',
        'Network/Data Flow Diagram',
        'Independent Vulnerability Assessment',
    ],
    'B': [
        'Vendor Technical Questionnaire',
        'Network/Data Flow Diagram',
    ],
    'C': [
        'Vendor Technical Questionnaire',
        'Network/Data Flow Diagram',
    ],
}

TIER_LABELS = {
    'A': 'Tier A — SaaS/Third Party with PHI/PII/PCI',
    'B': 'Tier B — UMMH On-Prem with PHI/PII/PCI',
    'C': 'Tier C — No Regulated Data',
}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_email TEXT,
            assigned_date TEXT,
            assigned_to TEXT,
            outreach_sent INTEGER DEFAULT 0,
            outreach_date TEXT,
            status TEXT DEFAULT 'Pending',
            owner TEXT,
            business_owner TEXT,
            support_group TEXT,
            vendor_contact TEXT,
            writeup_submitted INTEGER DEFAULT 0,
            writeup_date TEXT,
            tier TEXT DEFAULT 'A',
            medical_device INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER,
            doc_type TEXT,
            received INTEGER DEFAULT 0,
            received_date TEXT,
            comment TEXT,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER,
            note TEXT,
            author TEXT,
            timestamp TEXT,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        );
    ''')
    for col in ['owner','business_owner','support_group','vendor_contact','writeup_submitted','writeup_date','tier','medical_device']:
        try:
            conn.execute(f'ALTER TABLE vendors ADD COLUMN {col} TEXT')
        except: pass
    try:
        conn.execute('ALTER TABLE documents ADD COLUMN comment TEXT')
    except: pass
    conn.commit()
    conn.close()

def get_docs_for_tier(tier, medical_device):
    docs = list(TIER_DOCS.get(tier, TIER_DOCS['A']))
    if medical_device:
        docs.append('MDS2 (Medical Device)')
    return docs

def is_manager():
    return session.get('role') == 'manager'

def current_user():
    return session.get('user', None)

def get_deadline_info(outreach_date):
    if not outreach_date:
        return None, False
    od = datetime.strptime(outreach_date, '%Y-%m-%d')
    deadline = od + timedelta(days=3)
    overdue = datetime.now() > deadline
    return deadline.strftime('%Y-%m-%d'), overdue

def build_vendor_data(vendors, conn):
    result = []
    for v in vendors:
        docs = conn.execute('SELECT * FROM documents WHERE vendor_id = ?', (v['id'],)).fetchall()
        received = sum(1 for d in docs if d['received'])
        deadline, overdue = get_deadline_info(v['outreach_date'])
        result.append({'vendor': v, 'docs_received': received, 'docs_total': len(docs), 'deadline': deadline, 'overdue': overdue})
    return result

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        choice = request.form.get('choice')
        password = request.form.get('password', '')
        if choice == 'manager':
            if password == MANAGER_PASSWORD:
                session['role'] = 'manager'
                session['user'] = 'Manager'
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', analysts=ANALYSTS, error='Incorrect manager password.')
        else:
            session['role'] = 'analyst'
            session['user'] = choice
            return redirect(url_for('dashboard'))
    return render_template('login.html', analysts=ANALYSTS, error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not current_user():
        return redirect(url_for('login'))
    search = request.args.get('search', '').strip()
    filter_assignee = request.args.get('assignee', '').strip()
    filter_status = request.args.get('status', '').strip()
    conn = get_db()
    query = 'SELECT * FROM vendors WHERE 1=1'
    params = []
    if not is_manager():
        query += ' AND assigned_to = ?'
        params.append(current_user())
    elif filter_assignee:
        query += ' AND assigned_to = ?'
        params.append(filter_assignee)
    if search:
        query += ' AND (name LIKE ? OR contact_email LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    if filter_status:
        query += ' AND status = ?'
        params.append(filter_status)
    query += ' ORDER BY assigned_date DESC'
    vendors = conn.execute(query, params).fetchall()
    vendor_data = build_vendor_data(vendors, conn)
    analyst_stats = []
    if is_manager():
        for analyst in ANALYSTS:
            all_v = conn.execute('SELECT * FROM vendors WHERE assigned_to = ?', (analyst,)).fetchall()
            total = len(all_v)
            complete = sum(1 for v in all_v if v['status'] == 'Complete')
            overdue_count = sum(1 for v in all_v if get_deadline_info(v['outreach_date'])[1] and v['status'] != 'Complete')
            pending_review = sum(1 for v in all_v if v['status'] == 'Pending Review')
            analyst_stats.append({'name': analyst, 'total': total, 'complete': complete, 'active': total - complete, 'overdue': overdue_count, 'pending_review': pending_review})
    conn.close()
    return render_template('dashboard.html', vendor_data=vendor_data, is_manager=is_manager(), user=current_user(),
        analysts=ANALYSTS, analyst_stats=analyst_stats, search=search, filter_assignee=filter_assignee, filter_status=filter_status)

@app.route('/new', methods=['GET', 'POST'])
def new_vendor():
    if not is_manager():
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        assigned_to = request.form['assigned_to']
        owner = request.form.get('owner', '')
        business_owner = request.form.get('business_owner', '')
        support_group = request.form.get('support_group', '')
        vendor_contact = request.form.get('vendor_contact', '')
        tier = request.form.get('tier', 'A')
        medical_device = 1 if request.form.get('medical_device') else 0
        date = datetime.now().strftime('%Y-%m-%d')
        conn = get_db()
        cur = conn.execute(
            'INSERT INTO vendors (name, contact_email, assigned_date, assigned_to, owner, business_owner, support_group, vendor_contact, tier, medical_device) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (name, email, date, assigned_to, owner, business_owner, support_group, vendor_contact, tier, medical_device))
        vendor_id = cur.lastrowid
        for doc in get_docs_for_tier(tier, medical_device):
            conn.execute('INSERT INTO documents (vendor_id, doc_type) VALUES (?, ?)', (vendor_id, doc))
        conn.commit()
        conn.close()
        return redirect(url_for('vendor_detail', vendor_id=vendor_id))
    return render_template('new_vendor.html', analysts=ANALYSTS, tier_labels=TIER_LABELS, tier_docs=TIER_DOCS)

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    if not current_user():
        return redirect(url_for('login'))
    conn = get_db()
    vendor = conn.execute('SELECT * FROM vendors WHERE id = ?', (vendor_id,)).fetchone()
    if not is_manager() and vendor['assigned_to'] != current_user():
        return redirect(url_for('dashboard'))
    docs = conn.execute('SELECT * FROM documents WHERE vendor_id = ?', (vendor_id,)).fetchall()
    notes = conn.execute('SELECT * FROM notes WHERE vendor_id = ? ORDER BY timestamp DESC', (vendor_id,)).fetchall()
    conn.close()
    missing = [d['doc_type'] for d in docs if not d['received']]
    all_docs_received = len(missing) == 0
    deadline, overdue = get_deadline_info(vendor['outreach_date'])
    tier_label = TIER_LABELS.get(vendor['tier'], '')
    return render_template('vendor_detail.html', vendor=vendor, docs=docs, notes=notes,
                           missing=missing, all_docs_received=all_docs_received,
                           is_manager=is_manager(), user=current_user(),
                           deadline=deadline, overdue=overdue, analysts=ANALYSTS,
                           tier_label=tier_label)

@app.route('/vendor/<int:vendor_id>/toggle_doc/<int:doc_id>', methods=['POST'])
def toggle_doc(vendor_id, doc_id):
    if not current_user():
        return redirect(url_for('login'))
    conn = get_db()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    new_val = 0 if doc['received'] else 1
    received_date = datetime.now().strftime('%Y-%m-%d') if new_val else None
    conn.execute('UPDATE documents SET received = ?, received_date = ? WHERE id = ?', (new_val, received_date, doc_id))
    vendor = conn.execute('SELECT * FROM vendors WHERE id = ?', (vendor_id,)).fetchone()
    if vendor['status'] not in ('Pending Review', 'Complete'):
        docs = conn.execute('SELECT * FROM documents WHERE vendor_id = ?', (vendor_id,)).fetchall()
        all_received = all(d['received'] for d in docs)
        status = 'Docs Received' if all_received else 'In Progress'
        conn.execute('UPDATE vendors SET status = ? WHERE id = ?', (status, vendor_id))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/update_doc_comment/<int:doc_id>', methods=['POST'])
def update_doc_comment(vendor_id, doc_id):
    if not current_user():
        return redirect(url_for('login'))
    comment = request.form.get('comment', '')
    conn = get_db()
    conn.execute('UPDATE documents SET comment = ? WHERE id = ?', (comment, doc_id))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/add_note', methods=['POST'])
def add_note(vendor_id):
    if not current_user():
        return redirect(url_for('login'))
    note = request.form['note']
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = get_db()
    conn.execute('INSERT INTO notes (vendor_id, note, author, timestamp) VALUES (?, ?, ?, ?)',
                 (vendor_id, note, current_user(), timestamp))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/mark_outreach', methods=['POST'])
def mark_outreach(vendor_id):
    if not current_user():
        return redirect(url_for('login'))
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    conn.execute('UPDATE vendors SET outreach_sent = 1, outreach_date = ?, status = "Awaiting Documents" WHERE id = ?', (today, vendor_id))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/submit_writeup', methods=['POST'])
def submit_writeup(vendor_id):
    if not current_user():
        return redirect(url_for('login'))
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    conn.execute('UPDATE vendors SET writeup_submitted = 1, writeup_date = ?, status = "Pending Review" WHERE id = ?', (today, vendor_id))
    conn.execute('INSERT INTO notes (vendor_id, note, author, timestamp) VALUES (?, ?, ?, ?)',
                 (vendor_id, 'Write-up submitted for manager review.', current_user(), today))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/reassign', methods=['POST'])
def reassign(vendor_id):
    if not is_manager():
        return redirect(url_for('dashboard'))
    assigned_to = request.form['assigned_to']
    conn = get_db()
    conn.execute('UPDATE vendors SET assigned_to = ? WHERE id = ?', (assigned_to, vendor_id))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/complete', methods=['POST'])
def complete_vendor(vendor_id):
    if not is_manager():
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute('UPDATE vendors SET status = "Complete" WHERE id = ?', (vendor_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/vendor/<int:vendor_id>/request_revision', methods=['POST'])
def request_revision(vendor_id):
    if not is_manager():
        return redirect(url_for('dashboard'))
    note = request.form.get('revision_note', '')
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = get_db()
    conn.execute('UPDATE vendors SET status = "In Progress", writeup_submitted = 0 WHERE id = ?', (vendor_id,))
    if note:
        conn.execute('INSERT INTO notes (vendor_id, note, author, timestamp) VALUES (?, ?, ?, ?)',
                     (vendor_id, f'[REVISION REQUESTED] {note}', 'Manager', today))
    conn.commit()
    conn.close()
    return redirect(url_for('vendor_detail', vendor_id=vendor_id))

@app.route('/vendor/<int:vendor_id>/delete', methods=['POST'])
def delete_vendor(vendor_id):
    if not is_manager():
        return redirect(url_for('dashboard'))
    conn = get_db()
    conn.execute('DELETE FROM documents WHERE vendor_id = ?', (vendor_id,))
    conn.execute('DELETE FROM notes WHERE vendor_id = ?', (vendor_id,))
    conn.execute('DELETE FROM vendors WHERE id = ?', (vendor_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
