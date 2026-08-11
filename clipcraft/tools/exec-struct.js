const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3').verbose();
const db = new sqlite3.Database('/root/.n8n/database.sqlite');
const EXEC_ID = process.argv[2] || '46907';

db.get("SELECT data FROM execution_data WHERE executionId = ?", [String(EXEC_ID)], (e, row) => {
  if (e) { console.error('err', e.message); db.close(); return; }
  if (!row) { console.error('no row'); db.close(); return; }
  let run;
  try { run = JSON.parse(row.data); } catch (x) { console.error('parse fail', x.message); db.close(); return; }
  function keys(o) { return o && typeof o === 'object' ? Object.keys(o).join(',') : typeof o; }
  console.log('TOP keys:', keys(run));
  if (run.resultData) {
    console.log('resultData keys:', keys(run.resultData));
    console.log('runData keys:', keys(run.resultData.runData));
    if (run.resultData.runData) {
      for (const n of Object.keys(run.resultData.runData)) {
        console.log('RUN NODE:', n);
      }
    }
  }
  if (run.data) console.log('data top:', keys(run.data));
  db.close();
});