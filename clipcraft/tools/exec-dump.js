const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3').verbose();
const db = new sqlite3.Database('/root/.n8n/database.sqlite');
const EXEC_ID = process.argv[2] || '46907';

db.get("SELECT executionId, data FROM execution_data WHERE executionId = ?", [String(EXEC_ID)], (e, row) => {
  if (e) { console.error('column err', e.message); listColumns(); return; }
  if (!row) { console.error('No row via executionId/id'); listColumns(); return; }
  printRun(JSON.parse(row.data));
});

function listColumns() {
  db.all("PRAGMA table_info(execution_data)", (e, cols) => {
    console.log('COLS:', cols.map(c => c.name).join(','));
    db.all("SELECT * FROM execution_data LIMIT 3", (e2, rows) => {
      console.log('ROWS:', JSON.stringify(rows).slice(0, 300));
      db.close();
    });
  });
}

function printRun(run) {
  const runData = run && run.resultData && run.resultData.runData;
  if (!runData) { console.error('no runData'); console.log(JSON.stringify(run).slice(0, 4096)); return; }
  for (const nodeName of Object.keys(runData)) {
    const runs = runData[nodeName];
    if (!runs || !runs.length) continue;
    const first = runs[0];
    const out = first.data && first.data.main && first.data.main[0];
    console.log('===== NODE:', nodeName, '=====');
    if (out && out.length) {
      out.forEach((o, i) => console.log(`  [out ${i}]`, JSON.stringify(o.json ?? null).slice(0, 900)));
    } else {
      console.log('  (no main output)');
    }
    if (first.error) console.log('  ERROR:', JSON.stringify(first.error).slice(0, 500));
  }
  db.close();
}