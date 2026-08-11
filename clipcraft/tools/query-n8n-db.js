const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3').verbose();
const db = new sqlite3.Database('/root/.n8n/database.sqlite');

const EXEC_ID = process.argv[2] || '46907';
const WORKFLOW_NAME = process.argv[3] || '';

db.all("SELECT name FROM sqlite_master WHERE type='table'", (e, tables) => {
  if (e) { console.error('ERR tables', e); process.exit(1); }
  console.log('TABLES:', tables.map(t => t.name).join(','));
  db.all("SELECT id, name FROM workflow_entity", (e2, wfs) => {
    if (e2) console.error('ERR wf', e2);
    else wfs.forEach(w => console.log('WF', w.id, w.name));
    db.all("SELECT id, workflowId, status, startedAt, finished FROM execution_entity WHERE id=? LIMIT 5", [EXEC_ID], (e3, rows) => {
      if (e3) { console.error('ERR exec', e3); }
      console.log('EXEC ROWS:', JSON.stringify(rows));
    });
  });
  setTimeout(() => db.close(), 300);
});