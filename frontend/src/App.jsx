import React, { useState, useEffect, useMemo } from 'react';
import './App.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const CATEGORIES = [
  'Food & Dining',
  'Transportation',
  'Shopping',
  'Utilities & Bills',
  'Entertainment',
  'Health & Fitness',
  'Education',
  'Other'
];

const CATEGORY_COLORS = {
  'Food & Dining': '#f97316',
  'Transportation': '#3b82f6',
  'Shopping': '#ec4899',
  'Utilities & Bills': '#10b981',
  'Entertainment': '#8b5cf6',
  'Health & Fitness': '#06b6d4',
  'Education': '#eab308',
  'Other': '#64748b'
};

export default function App() {
  const [expenses, setExpenses] = useState([]);
  const [totalData, setTotalData] = useState({ total: 0, cached: false });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [backendHealthy, setBackendHealthy] = useState(true);

  // Form State
  const todayStr = new Date().toISOString().split('T')[0];
  const [formData, setFormData] = useState({
    title: '',
    amount: '',
    category: 'Food & Dining',
    date: todayStr
  });

  // Fetch initial data
  const fetchData = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      // 1. Fetch expenses list
      const expRes = await fetch(`${API_BASE}/expenses`);
      if (!expRes.ok) throw new Error(`Failed to load expenses (${expRes.status})`);
      const expData = await expRes.json();
      setExpenses(expData);

      // 2. Fetch total (Redis-cached endpoint)
      const totalRes = await fetch(`${API_BASE}/expenses/total`);
      if (!totalRes.ok) throw new Error(`Failed to load total (${totalRes.status})`);
      const totData = await totalRes.json();
      setTotalData(totData);

      setBackendHealthy(true);
    } catch (err) {
      console.error('Fetch error:', err);
      setErrorMessage(
        `Unable to connect to backend at ${API_BASE}. Make sure the Docker containers are running.`
      );
      setBackendHealthy(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Form input changes
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  // Add Expense
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      setErrorMessage('Please enter an expense title.');
      return;
    }
    const parsedAmount = parseFloat(formData.amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setErrorMessage('Please enter a valid amount greater than 0.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    try {
      const response = await fetch(`${API_BASE}/expenses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: formData.title.trim(),
          amount: parsedAmount,
          category: formData.category,
          date: formData.date
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to add expense.');
      }

      // Reset form
      setFormData({
        title: '',
        amount: '',
        category: 'Food & Dining',
        date: todayStr
      });

      setSuccessMessage('Expense added successfully!');
      setTimeout(() => setSuccessMessage(null), 3000);

      // Refresh expenses & total
      await fetchData();
    } catch (err) {
      console.error('Error adding expense:', err);
      setErrorMessage(err.message || 'Error adding expense.');
    } finally {
      setSubmitting(false);
    }
  };

  // Delete Expense
  const handleDelete = async (id) => {
    setDeletingId(id);
    setErrorMessage(null);
    try {
      const response = await fetch(`${API_BASE}/expenses/${id}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete expense.');
      }

      setSuccessMessage('Expense removed.');
      setTimeout(() => setSuccessMessage(null), 2500);

      // Refresh list & total
      await fetchData();
    } catch (err) {
      console.error('Error deleting expense:', err);
      setErrorMessage(err.message || 'Could not delete expense.');
    } finally {
      setDeletingId(null);
    }
  };

  // Category wise calculation
  const categorySummary = useMemo(() => {
    const map = {};
    let sum = 0;
    expenses.forEach((item) => {
      const cat = item.category || 'Other';
      const amt = Number(item.amount) || 0;
      map[cat] = (map[cat] || 0) + amt;
      sum += amt;
    });

    return Object.entries(map).map(([name, amount]) => ({
      name,
      amount,
      percentage: sum > 0 ? ((amount / sum) * 100).toFixed(1) : 0,
      color: CATEGORY_COLORS[name] || '#64748b'
    })).sort((a, b) => b.amount - a.amount);
  }, [expenses]);

  return (
    <div className="app-wrapper">
      {/* Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-icon">₹</div>
          <div>
            <h1 className="brand-title">SpendLite</h1>
            <p className="brand-subtitle">Fast, Simple Expense Tracker with Redis Caching</p>
          </div>
        </div>

        <div className="header-status">
          <span className={`status-dot ${backendHealthy ? '' : 'offline'}`}></span>
          <span>{backendHealthy ? 'Backend Connected' : 'Offline / Error'}</span>
        </div>
      </header>

      {/* Error Banner */}
      {errorMessage && (
        <div className="error-banner">
          <span>⚠️ {errorMessage}</span>
          <button onClick={() => fetchData()}>Retry</button>
        </div>
      )}

      {/* Success Banner */}
      {successMessage && (
        <div className="success-banner">
          <span>✓ {successMessage}</span>
        </div>
      )}

      {/* Top Dashboard: Total Spending & Category Breakdown */}
      <div className="dashboard-grid">
        {/* Total Spending Card */}
        <div className="total-card">
          <div className="total-header">
            <span className="card-title">Total Spending</span>
            <span className={`cache-pill ${totalData.cached ? 'hit' : 'miss'}`}>
              {totalData.cached ? '⚡ Cached (Redis)' : '🔄 Freshly Computed'}
            </span>
          </div>

          <div className="total-amount">
            ₹ {Number(totalData.total || 0).toLocaleString('en-IN', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2
            })}
          </div>

          <div className="total-footer">
            <span>{expenses.length} transaction{expenses.length === 1 ? '' : 's'} recorded</span>
            <button className="refresh-btn" onClick={fetchData} title="Re-fetch total from backend">
              ↻ Refresh Total
            </button>
          </div>
        </div>

        {/* Category Breakdown Card */}
        <div className="category-summary-card">
          <span className="card-title">Category-wise Summary</span>
          {categorySummary.length === 0 ? (
            <p style={{ marginTop: '20px', color: 'var(--text-muted)', fontSize: '13px' }}>
              No expenses recorded yet to show category distribution.
            </p>
          ) : (
            <div className="category-list">
              {categorySummary.map((cat) => (
                <div key={cat.name} className="category-item">
                  <div className="category-info">
                    <span>{cat.name}</span>
                    <span>
                      ₹ {cat.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} ({cat.percentage}%)
                    </span>
                  </div>
                  <div className="category-bar-bg">
                    <div
                      className="category-bar-fill"
                      style={{ width: `${cat.percentage}%`, backgroundColor: cat.color }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Section: Form & Transaction List */}
      <div className="main-layout">
        {/* Add Expense Form */}
        <div className="form-card">
          <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '18px' }}>
            Add New Expense
          </h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="title">Title / Description</label>
              <input
                id="title"
                name="title"
                type="text"
                className="form-control"
                placeholder="e.g., Grocery Shopping"
                value={formData.title}
                onChange={handleInputChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="amount">Amount (₹)</label>
              <input
                id="amount"
                name="amount"
                type="number"
                step="0.01"
                min="0.01"
                className="form-control"
                placeholder="e.g., 450.00"
                value={formData.amount}
                onChange={handleInputChange}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="category">Category</label>
              <select
                id="category"
                name="category"
                className="form-control"
                value={formData.category}
                onChange={handleInputChange}
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="date">Date</label>
              <input
                id="date"
                name="date"
                type="date"
                className="form-control"
                value={formData.date}
                onChange={handleInputChange}
                required
              />
            </div>

            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Adding...' : '+ Add Expense'}
            </button>
          </form>
        </div>

        {/* Transactions List */}
        <div className="transactions-card">
          <div className="transactions-header">
            <h2 style={{ fontSize: '16px', fontWeight: 700 }}>Recent Transactions</h2>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {expenses.length} item{expenses.length === 1 ? '' : 's'}
            </span>
          </div>

          {loading ? (
            <div className="loading-indicator">
              <div className="spinner"></div>
              <span>Loading expenses...</span>
            </div>
          ) : expenses.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📋</div>
              <p style={{ fontWeight: 600 }}>No expenses yet</p>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                Add your first expense using the form to start tracking your spending.
              </p>
            </div>
          ) : (
            <div className="transaction-list">
              {expenses.map((item) => (
                <div key={item.id} className="transaction-item">
                  <div className="item-left">
                    <span
                      className="item-badge"
                      style={{
                        backgroundColor: `${CATEGORY_COLORS[item.category] || '#64748b'}20`,
                        color: CATEGORY_COLORS[item.category] || '#64748b'
                      }}
                    >
                      {item.category}
                    </span>
                    <div>
                      <div className="item-title">{item.title}</div>
                      <div className="item-date">{item.date}</div>
                    </div>
                  </div>

                  <div className="item-right">
                    <span className="item-amount">
                      ₹ {Number(item.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <button
                      className="delete-btn"
                      onClick={() => handleDelete(item.id)}
                      disabled={deletingId === item.id}
                      title="Delete expense"
                    >
                      {deletingId === item.id ? '...' : '🗑️'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
