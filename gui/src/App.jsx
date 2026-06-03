import React, { useState, useEffect } from 'react';

const API_URL = '/api';

function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [tableSchema, setTableSchema] = useState(null);
  const [inTransaction, setInTransaction] = useState(false);
  const [tableData, setTableData] = useState(null);

  useEffect(() => {
    fetchTables();
  }, []);

  const fetchTables = async () => {
    try {
      const res = await fetch(`${API_URL}/tables`);
      const data = await res.json();
      setTables(data.tables || []);
    } catch (e) {
      console.error(e);
    }
  };

  const executeQuery = async () => {
    setResult('');
    setError('');
    setTableData(null);
    const q = query.trim().endsWith(';') ? query.trim() : query.trim() + ';';
    try {
      const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q })
      });
      const data = await res.json();
      if (data.success) {
        if (data.is_table && data.headers) {
          setTableData({ headers: data.headers, rows: data.rows || [] });
        } else {
          setResult(data.result);
        }
        if (/create table|drop table/i.test(q)) fetchTables();
      } else {
        setError(data.error);
      }
    } catch (e) {
      setError(e.message);
    }
  };

  const showTableSchema = async (name) => {
    try {
      const res = await fetch(`${API_URL}/tables/${name}`);
      const data = await res.json();
      setSelectedTable(name);
      setTableSchema(data);
    } catch (e) {
      setError(e.message);
    }
  };

  const txBegin = async () => {
    try {
      const res = await fetch(`${API_URL}/transaction/begin`, { method: 'POST' });
      const data = await res.json();
      setResult(data.result);
      setInTransaction(true);
      setTableData(null);
      setError('');
    } catch (e) {
      setError(e.message);
    }
  };

  const txCommit = async () => {
    try {
      const res = await fetch(`${API_URL}/transaction/commit`, { method: 'POST' });
      const data = await res.json();
      setResult(data.result);
      setInTransaction(false);
      setTableData(null);
      fetchTables();
    } catch (e) {
      setError(e.message);
    }
  };

  const txRollback = async () => {
    try {
      const res = await fetch(`${API_URL}/transaction/rollback`, { method: 'POST' });
      const data = await res.json();
      setResult(data.result);
      setInTransaction(false);
      setTableData(null);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <h3>Tables</h3>
        <ul>
          {tables.map(t => (
            <li key={t} onClick={() => showTableSchema(t)} className={selectedTable === t ? 'active' : ''}>
              {t}
            </li>
          ))}
        </ul>
        {tableSchema && (
          <div className="schema">
            <h4>{tableSchema.name}</h4>
            <ul>
              {Object.entries(tableSchema.columns).map(([col, type]) => (
                <li key={col}>{col}: {type}</li>
              ))}
            </ul>
            {tableSchema.primary_key && <p>PK: {tableSchema.primary_key.join(', ')}</p>}
          </div>
        )}
      </aside>
      <main className="main">
        <h1>SQL DBMS</h1>
        <div className="tx-bar">
          <button onClick={txBegin} disabled={inTransaction}>BEGIN</button>
          <button onClick={txCommit} disabled={!inTransaction}>COMMIT</button>
          <button onClick={txRollback} disabled={!inTransaction}>ROLLBACK</button>
          {inTransaction && <span className="tx-badge">IN TRANSACTION</span>}
        </div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Enter SQL query..."
          rows={5}
        />
        <button onClick={executeQuery}>Execute</button>
        {error && <div className="error">{error}</div>}
        {result && !tableData && <pre className="result-text">{result}</pre>}
        {tableData && (
          <div className="table-container">
            <table className="result-table">
              <thead>
                <tr>
                  {tableData.headers.map((h, i) => (
                    <th key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableData.rows.length === 0 ? (
                  <tr>
                    <td colSpan={tableData.headers.length} className="empty-row">
                      No rows returned
                    </td>
                  </tr>
                ) : (
                  tableData.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j}>{cell}</td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
