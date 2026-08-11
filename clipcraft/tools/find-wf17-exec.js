const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3').verbose();
const db = new sqlite3.Database('/root/.n8n/database.sqlite');
const JOB = process.argv[2] || '7ce68c05-64ac-449b-a71a-69fe89978e9d';

db.all("SELECT id, workflowId FROM execution_entity ORDER BY id DESC LIMIT 300", [], (e, rows) => {
  if (e) { console.error('err', e.message); db.close(); return; }
  const wf17 = rows.filter(r => r.workflowId === '17');
  console.log('recent WF17 executions:', JSON.stringify(wf17.map(r => r.id)));
  db.close();
});