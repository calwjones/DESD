import { useState, useEffect } from 'react'
import axios from 'axios'
import './style.css'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'
const ORDER_API_URL = import.meta.env.VITE_ORDER_API_URL || 'http://localhost:8002'
const DESD_URL = import.meta.env.VITE_DESD_URL || 'http://localhost:8089';

function ContributionRow({ feature, value, shap, maxAbsShap }) {
  const sign = shap >= 0 ? 'positive' : 'negative'
  const width = maxAbsShap > 0 ? (Math.abs(shap) / maxAbsShap) * 100 : 0
  return (
    <div className="contribution-row">
      <div className="contribution-label">
        {feature}
        <span style={{ color: 'var(--muted)', fontSize: '0.75rem', marginLeft: '0.4rem' }}>
          ({value})
        </span>
      </div>
      <div className="contribution-bar-track">
        <div
          className={`contribution-bar-fill ${sign}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="contribution-value">
        {shap >= 0 ? '+' : ''}{shap.toFixed(3)}
      </div>
    </div>
  )
}

function ScoreBar({ label, value, compact = false }) {
  const safeValue = Math.max(0, Math.min(100, value ?? 0))
  return (
    <div className={compact ? 'score-bar-compact' : 'score-bar'}>
      <div className="score-bar-header">
        <span>{label}</span>
        <span>{safeValue.toFixed(0)}%</span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${safeValue}%` }} />
      </div>
    </div>
  )
}
 
 
// Mock accuracy data over time
const mockAccuracyData = [
  { date: 'Apr 8', accuracy: 82 },
  { date: 'Apr 9', accuracy: 84 },
  { date: 'Apr 10', accuracy: 86 },
  { date: 'Apr 11', accuracy: 88 },
  { date: 'Apr 12', accuracy: 87 },
  { date: 'Apr 13', accuracy: 89 },
  { date: 'Apr 14', accuracy: 91 },
  { date: 'Apr 15', accuracy: 90 }
]
// mock quality predictions 
const mockPredictions = [
  {
    id: 1,
    timestamp: '2026-04-15 14:23',
    product: 'Tomatoes',
    producer: 'Green Fields Farm',
    grade: 'B',
    color_score: 68.0,
    size_score: 85.0,
    ripeness_score: 72.0,
    confidence: 0.87,
    model_version: 'v1.2'
  },
  {
    id: 2,
    timestamp: '2026-04-15 13:45',
    product: 'Apples',
    producer: 'Orchard Valley',
    grade: 'A',
    color_score: 88.0,
    size_score: 90.0,
    ripeness_score: 85.0,
    confidence: 0.94,
    model_version: 'v1.2'
  },
  {
    id: 3,
    timestamp: '2026-04-15 12:10',
    product: 'Bananas',
    producer: 'Tropical Imports',
    grade: 'C',
    color_score: 58.0,
    size_score: 70.0,
    ripeness_score: 55.0,
    confidence: 0.78,
    model_version: 'v1.2'
  },
  {
    id: 4,
    timestamp: '2026-04-15 11:30',
    product: 'Carrots',
    producer: 'Root & Co',
    grade: 'A',
    color_score: 85.0,
    size_score: 88.0,
    ripeness_score: 80.0,
    confidence: 0.91,
    model_version: 'v1.2'
  },
  {
    id: 5,
    timestamp: '2026-04-15 10:15',
    product: 'Oranges',
    producer: 'Citrus Grove',
    grade: 'B',
    color_score: 75.0,
    size_score: 82.0,
    ripeness_score: 70.0,
    confidence: 0.85,
    model_version: 'v1.2'
  }
]
 
function formatTimestamp(ts) {
  if (!ts) return '—'
  if (ts.includes('T')) {
    const d = new Date(ts)
    if (!isNaN(d)) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  }
  const parts = ts.split(' ')
  return parts.length > 1 ? parts[1] : ts
}

function mapDesdLog(entry) {
  const p = entry.prediction || {}
  return {
    id: entry.id ?? `${entry.created_at}-${entry.user}`,
    timestamp: entry.created_at || entry.timestamp || '',
    product: entry.input_data?.product_id != null
      ? `Product #${entry.input_data.product_id}`
      : 'Unknown',
    grade: p.grade || '—',
    color_score: p.color_score ?? 0,
    size_score: p.size_score ?? 0,
    ripeness_score: p.ripeness_score ?? 0,
    confidence: entry.confidence_score ?? p.confidence ?? 0,
    model_version: entry.model_version || p.model_version || '—',
  }
}

function App() {
  const [selectedImage, setSelectedImage] = useState(null)
  const [accuracyData, setAccuracyData] = useState([]);
  const [imagePreview, setImagePreview] = useState(null)
  const [explanation, setExplanation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [recentPredictions, setRecentPredictions] = useState(mockPredictions)
  const [usingMockData, setUsingMockData] = useState(true)
  const [overrideState, setOverrideState] = useState('idle')
  const [correctedGrade, setCorrectedGrade] = useState('')
  const [overrideSubmitting, setOverrideSubmitting] = useState(false)
  const [shapCustomerId, setShapCustomerId] = useState('')
  const [shapProductId, setShapProductId] = useState('')
  const [shapResult, setShapResult] = useState(null)
  const [shapLoading, setShapLoading] = useState(false)
  const [shapError, setShapError] = useState(null)
  const [challenges, setChallenges] = useState([]);

useEffect(() => {
    let cancelled = false
    axios.get(`${API_URL}/interactions`, { params: { service_type: 'quality' } })
      .then(response => {
        if (cancelled) return
        const rows = Array.isArray(response.data) ? response.data : []
        
        // Regular predictions (non-overrides)
        const mapped = rows
          .filter(r => !r.user_override)
          .map(mapDesdLog)
        if (mapped.length > 0) {
          setPredictions(mapped)
          setUsingMockData(false)
        }

        // Challenged grades (overrides only)
        const overrides = rows.filter(r => r.user_override)
        setChallenges(overrides)
      })
      .catch(err => {
        console.warn('Could not fetch recent predictions, using mock:', err.message)
      })
    return () => { cancelled = true }
  }, [])

  const handleImageUpload = (event) => {
    const file = event.target.files[0]
    if (file) {
      setSelectedImage(file)
      setImagePreview(URL.createObjectURL(file))
      setExplanation(null)
      setOverrideState('idle')
      setCorrectedGrade('')
    }
  }

  const handleShapExplain = async () => {
    if (!shapCustomerId || !shapProductId) return
    setShapLoading(true)
    setShapError(null)
    setShapResult(null)
    try {
      const response = await axios.post(`${ORDER_API_URL}/explain`, {
        customer_id: parseInt(shapCustomerId, 10),
        product_id: parseInt(shapProductId, 10),
      })
      setShapResult(response.data)
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setShapError(detail)
    } finally {
      setShapLoading(false)
    }
  }

  const handleOverride = async () => {
    if (!correctedGrade || !explanation) return
    setOverrideSubmitting(true)
    try {
      await axios.post(`${API_URL}/override`, {
        original_log_id: explanation.log_id ?? null,
        corrected_grade: correctedGrade,
        product_id: 123,
        user_id: null,
      })
      setOverrideState('done')
    } catch (err) {
      console.error('Override submission failed:', err)
      alert('Could not record correction. Is the API running?')
    } finally {
      setOverrideSubmitting(false)
    }
  }

  const [predictions, setPredictions] = useState([]);
  const [predictionsLoading, setPredictionsLoading] = useState(true);

  const API_URL = import.meta.env.VITE_AI_SERVICE_URL || 'http://localhost:8001';

  useEffect(() => {
    const fetchInteractions = async () => {
      try {
        const res = await fetch(`${API_URL}/interactions?service_type=quality`);
        const data = await res.json();
        
        const mapped = data.map(item => ({
          id: item.id,
          timestamp: new Date(item.timestamp).toLocaleTimeString('en-GB', { 
            hour: '2-digit', minute: '2-digit' 
          }),
          product: item.input_data?.filename?.replace('products/', '').replace(/\.\w+$/, '') || 'Unknown',
          producer: item.input_data?.user_id ? `User ${item.input_data.user_id}` : 'Unknown',
          grade: item.prediction?.grade || '—',
          color_score: item.prediction?.color_score || 0,
          size_score: item.prediction?.size_score || 0,
          ripeness_score: item.prediction?.ripeness_score || 0,
          confidence: item.prediction?.confidence || 0,
        }));
        
        setPredictions(mapped);
      // Build confidence trend from live data
      const byDay = {};
      data.forEach(item => {
        const date = new Date(item.timestamp).toLocaleDateString('en-GB', { 
          month: 'short', day: 'numeric' 
        });
        if (!byDay[date]) byDay[date] = { total: 0, count: 0 };
        byDay[date].total += (item.prediction?.confidence || 0);
        byDay[date].count += 1;
      });

      const trend = Object.entries(byDay).map(([date, val]) => ({
        date,
        accuracy: parseFloat(((val.total / val.count) * 100).toFixed(1)),
      }));

      setAccuracyData(trend.reverse());
      } catch (err) {
        console.error('Failed to fetch interactions:', err);
      } finally {
        setPredictionsLoading(false);
      }
    };

    fetchInteractions();
    const interval = setInterval(fetchInteractions, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);
 
  const confidenceByDay = predictions.reduce((acc, pred) => {
    const date = new Date(pred.timestamp).toLocaleDateString('en-GB', { 
      month: 'short', day: 'numeric' 
    });
    if (!acc[date]) acc[date] = { total: 0, count: 0 };
    acc[date].total += pred.confidence;
    acc[date].count += 1;
    return acc;
  }, {});

  // const accuracyData = Object.entries(confidenceByDay).map(([date, val]) => ({
  //   date,
  //   accuracy: ((val.total / val.count) * 100).toFixed(1),
  // }));

  const handleExplain = async () => {
    if (!selectedImage) return
    
    setLoading(true)
    
    try {
      const formData = new FormData()
      formData.append('image', selectedImage)
      formData.append('product_id', 123)
      
      const response = await axios.post(`${API_URL}/explain`, formData)
      setExplanation(response.data)
    } catch (error) {
      console.error('Error getting explanation:', error)
      alert('Failed to get explanation. Is the API running?')
    } finally {
      setLoading(false)
    }
  }
  const handleReviewChallenge = async (filename) => {
    try {
      const imageUrl = `${DESD_URL}/media/${filename}`;
      const response = await fetch(imageUrl);
      const blob = await response.blob();
      const file = new File([blob], filename, { type: blob.type });
      
      // Set the image into the existing upload flow
      setSelectedImage(file);
      setImagePreview(URL.createObjectURL(blob));
      
      // Auto-scroll to the upload section
      document.getElementById('file-upload')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (err) {
      console.error('Failed to fetch product image:', err);
      alert('Could not load product image from marketplace');
    }
  };
  const overallAvg = accuracyData.length > 0 
    ? (accuracyData.reduce((sum, d) => sum + d.accuracy, 0) / accuracyData.length).toFixed(1)
    : 0;

  const [currentPage, setCurrentPage] = useState(1);
  const perPage = 10;
  const totalPages = Math.ceil(predictions.length / perPage);
  const paginatedPredictions = predictions.slice((currentPage - 1) * perPage, currentPage * perPage);
 
  return (
    <>
      {/* Simplified Navbar */}
      <nav className="navbar">
        <div className="navbar-brand">DESD Marketplace - Quality Analysis</div>
      </nav>
 
      {/* Full width container */}
      
      <div style={{ 
        maxWidth: '1200px', 
        margin: '0 auto',
        padding: '2rem 1.5rem'
      }}>
        {/* Page Header */}
        <div className="dashboard-header">
          <h1>Quality Analysis Dashboard</h1>
        </div>
 
 
        {/* Accuracy Monitoring Chart */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ 
            fontSize: '1.1rem', 
            fontWeight: '600', 
            marginBottom: '0.5rem', 
            color: 'var(--text)' 
          }}>
            Average Model Confidence Over Time
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '1.5rem' }}>
            7-day rolling confidence
          </p>
          
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={accuracyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ddd" />
              <XAxis 
                dataKey="date" 
                style={{ fontSize: '0.8rem', fill: 'var(--muted)' }}
              />
              <YAxis 
                domain={[75, 100]}
                style={{ fontSize: '0.8rem', fill: 'var(--muted)' }}
                tickFormatter={(value) => `${value}%`}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '0.85rem'
                }}
                formatter={(value) => [`${value}%`, 'Accuracy']}
              />
              <Line 
                type="monotone" 
                dataKey="accuracy" 
                stroke="var(--accent)" 
                strokeWidth={2.5}
                dot={{ fill: 'var(--accent)', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
          
          {/* Alert threshold indicator */}
          {accuracyData.length > 0 && (
            <div style={{ 
              marginTop: '1rem', 
              padding: '0.75rem 1rem',
              backgroundColor: accuracyData[accuracyData.length - 1]?.accuracy >= 85 ? '#e8f5eb' : '#fde8e8',
              border: `1px solid ${accuracyData[accuracyData.length - 1]?.accuracy >= 85 ? '#b0d8b8' : '#d8b0b0'}`,
              borderRadius: 'var(--radius)',
              fontSize: '0.85rem',
              color: accuracyData[accuracyData.length - 1]?.accuracy >= 85 ? '#1a5c2a' : '#8b1a1a'
            }}>
              <strong>Status:</strong> {
                overallAvg >= 85 
                  ? `Model confidence is healthy. Average: ${overallAvg}% (above 85% threshold)`
                  : `Model confidence below threshold. Average: ${overallAvg}% (below 85% threshold)`
              }
            </div>
          )}
        </div>
        
        {/* Recent Predictions Table */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ 
            fontSize: '1.1rem', 
            fontWeight: '600', 
            marginBottom: '1rem', 
            color: 'var(--text)' 
          }}>
            Recent Quality Assessments
          </h2>
          
          {usingMockData && (
            <p style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
              Showing sample data — live DESD log feed unavailable.
            </p>
          )}

          <table className="product-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Product</th>
                <th>Grade</th>
                <th>Scores</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {paginatedPredictions.length === 0 && !predictionsLoading ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted)' }}>
                  No assessments yet
                </td></tr>
              ) : paginatedPredictions.map(pred => (
                <tr key={pred.id}>
                  <td>{formatTimestamp(pred.timestamp)}</td>
                  <td>{pred.product}</td>
                  <td>
                    <strong style={{
                      color: pred.grade === 'A' ? 'var(--accent)' :
                            pred.grade === 'C' ? '#c0392b' : 'var(--text)'
                    }}>
                      Grade {pred.grade}
                    </strong>
                  </td>
                  <td style={{ minWidth: '160px' }}>
                    <ScoreBar label="C" value={pred.color_score} compact />
                    <ScoreBar label="S" value={pred.size_score} compact />
                    <ScoreBar label="R" value={pred.ripeness_score} compact />
                  </td>
                  <td>{(pred.confidence * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginTop: '1rem' }}>
              <button 
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', cursor: currentPage === 1 ? 'default' : 'pointer', opacity: currentPage === 1 ? 0.4 : 1 }}
              >
                Previous
              </button>
              <span style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                Page {currentPage} of {totalPages}
              </span>
              <button 
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', cursor: currentPage === totalPages ? 'default' : 'pointer', opacity: currentPage === totalPages ? 0.4 : 1 }}
              >
                Next
              </button>
            </div>
          )}
        </div>
 
        {/* Challenged Grades */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600', marginBottom: '1rem', color: 'var(--text)' }}>
            Challenged Grades
          </h2>
          {challenges.length === 0 ? (
            <p style={{ color: 'var(--muted)', fontStyle: 'italic' }}>No challenged grades</p>
          ) : (
            <table className="product-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Product</th>
                  <th>AI Grade</th>
                  <th>Suggested Grade</th>
                  <th>Reason</th>
                  <th>Image</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {challenges.map(c => (
                  <tr key={c.id}>
                    <td>{new Date(c.timestamp).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                    <td>{c.input_data?.filename?.replace('products/', '').replace(/\.\w+$/, '') || 'Unknown'}</td>
                    <td>
                      <strong style={{ color: '#c0392b' }}>
                        Grade {c.override_value?.original_grade || c.prediction?.grade}
                      </strong>
                    </td>
                    <td>
                      <strong style={{ color: 'var(--accent)' }}>
                        Grade {c.override_value?.suggested_grade}
                      </strong>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                      {c.override_value?.reason || '—'}
                    </td>
                    <td>
                      {c.input_data?.filename && (
                        <img 
                          src={`${DESD_URL}/media/${c.input_data.filename}`} 
                          alt="Product"
                          style={{ width: '50px', height: '50px', objectFit: 'cover', borderRadius: '4px' }}
                        />
                      )}
                    </td>
                    <td>
                      {c.override_value?.resolved ? (
                        <span style={{ 
                          fontSize: '0.8rem', 
                          fontWeight: 600,
                          color: c.override_value.resolved === 'approved' ? 'var(--accent)' : '#c0392b' 
                        }}>
                          {c.override_value.resolved === 'approved' ? '✓ Approved' : '✗ Rejected'}
                        </span>
                      ) : (
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button
                            onClick={async () => {
                              try {
                                await axios.post(`${DESD_URL}/api/ai-logs/${c.id}/resolve/`, { action: 'approve' })
                                setChallenges(prev => prev.map(ch => 
                                  ch.id === c.id ? { ...ch, override_value: { ...ch.override_value, resolved: 'approved' } } : ch
                                ))
                              } catch (err) { console.error('Approve failed:', err) }
                            }}
                            style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer' }}
                          >
                            Approve
                          </button>
                          <button
                            onClick={async () => {
                              try {
                                await axios.post(`${DESD_URL}/api/ai-logs/${c.id}/resolve/`, { action: 'reject' })
                                setChallenges(prev => prev.map(ch => 
                                  ch.id === c.id ? { ...ch, override_value: { ...ch.override_value, resolved: 'rejected' } } : ch
                                ))
                              } catch (err) { console.error('Reject failed:', err) }
                            }}
                            style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', background: '#c0392b', color: '#fff', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer' }}
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </td>
                    <td>
                        <button
                          onClick={() => handleReviewChallenge(c.input_data?.filename)}
                          style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', background: '#6c757d', color: '#fff', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer' }}
                        >
                          Review
                        </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {/* Order Prediction SHAP Card */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600', marginBottom: '0.5rem', color: 'var(--text)' }}>
            Explain an Order Recommendation
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '1rem' }}>
            Enter a customer and product to see which features pushed the reorder probability up or down (SHAP).
          </p>

          <div className="shap-form">
            <div>
              <label>Customer ID</label>
              <input
                type="number"
                value={shapCustomerId}
                onChange={e => setShapCustomerId(e.target.value)}
                placeholder="e.g. 1"
              />
            </div>
            <div>
              <label>Product ID</label>
              <input
                type="number"
                value={shapProductId}
                onChange={e => setShapProductId(e.target.value)}
                placeholder="e.g. 42"
              />
            </div>
            <button
              className="btn"
              onClick={handleShapExplain}
              disabled={!shapCustomerId || !shapProductId || shapLoading}
            >
              {shapLoading ? 'Explaining...' : 'Explain'}
            </button>
          </div>

          {shapError && (
            <p style={{ color: '#c0392b', fontSize: '0.85rem' }}>{shapError}</p>
          )}

          {shapResult && (
            <div>
              <p style={{ marginBottom: '1rem' }}>
                <strong>Reorder probability:</strong> {(shapResult.reorder_probability * 100).toFixed(1)}%
                <span style={{ color: 'var(--muted)', marginLeft: '1rem', fontSize: '0.85rem' }}>
                  (base {(shapResult.base_value * 100).toFixed(1)}%)
                </span>
              </p>

              {shapResult.top_positive.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '0.5rem' }}>
                    Features pushing probability up
                  </h3>
                  {shapResult.top_positive.map(c => (
                    <ContributionRow
                      key={`pos-${c.feature}`}
                      feature={c.feature}
                      value={c.value}
                      shap={c.shap}
                      maxAbsShap={Math.max(
                        ...shapResult.top_positive.map(x => Math.abs(x.shap)),
                        ...shapResult.top_negative.map(x => Math.abs(x.shap)),
                      )}
                    />
                  ))}
                </>
              )}

              {shapResult.top_negative.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: '600', margin: '1rem 0 0.5rem 0' }}>
                    Features pushing probability down
                  </h3>
                  {shapResult.top_negative.map(c => (
                    <ContributionRow
                      key={`neg-${c.feature}`}
                      feature={c.feature}
                      value={c.value}
                      shap={c.shap}
                      maxAbsShap={Math.max(
                        ...shapResult.top_positive.map(x => Math.abs(x.shap)),
                        ...shapResult.top_negative.map(x => Math.abs(x.shap)),
                      )}
                    />
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* Upload Card */}
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{
            fontSize: '1.1rem',
            fontWeight: '600',
            marginBottom: '1rem',
            color: 'var(--text)',
            textAlign: 'center'
          }}>
            Upload Product Image
          </h2>
          <div style={{ marginBottom: '1rem', textAlign: 'center' }}>
            <label htmlFor="file-upload" className="btn" style={{ 
              cursor: 'pointer',
              display: 'inline-block'
            }}>
              Choose Image
            </label>
            <input 
              id="file-upload"
              type="file" 
              accept="image/*" 
              onChange={handleImageUpload}
              style={{ display: 'none' }}
            />
            {selectedImage && (
              <span style={{ 
                marginLeft: '1rem', 
                color: 'var(--muted)',
                fontSize: '0.9rem'
              }}>
                {selectedImage.name}
              </span>
            )}
          </div>
          
          {imagePreview && (
            <div style={{ textAlign: 'center' }}>
              <img 
                src={imagePreview} 
                alt="Product" 
                style={{ 
                  maxHeight: '400px',
                  maxWidth: '100%',
                  marginBottom: '1rem',
                  borderRadius: 'var(--radius)'
                }}
              />
              <br />
              <button 
                className="btn"
                onClick={handleExplain} 
                disabled={loading}
              >
                {loading ? 'Analyzing...' : 'Analyze Quality'}
              </button>
            </div>
          )}
        </div>
 
        {/* Results */}
        {explanation && (
          <>
            {/* Summary Cards */}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: '1rem',
              marginBottom: '1.5rem'
            }}>
              <div className="card">
                <div style={{ 
                  fontSize: '0.75rem', 
                  fontWeight: '600',
                  color: '#666',
                  textTransform: 'uppercase',
                  marginBottom: '0.5rem',
                  letterSpacing: '0.5px'
                }}>
                  Classification
                </div>
                <p style={{ 
                  fontSize: '1.4rem', 
                  fontWeight: '600', 
                  color: 'var(--text)',
                  margin: 0
                }}>
                  {explanation.predicted_class}
                </p>
              </div>
              <div className="card">
                <div style={{ 
                  fontSize: '0.75rem', 
                  fontWeight: '600',
                  color: '#666',
                  textTransform: 'uppercase',
                  marginBottom: '0.5rem',
                  letterSpacing: '0.5px'
                }}>
                  Confidence Level
                </div>
                <p style={{ 
                  fontSize: '1.4rem', 
                  fontWeight: '600', 
                  color: 'var(--accent)',
                  margin: 0
                }}>
                  {(explanation.confidence * 100).toFixed(1)}%
                </p>
              </div>
              
              {/* Quality Assessment Card */}
              {explanation.grade && (
                <div className="card">
                  <div style={{ 
                    fontSize: '0.75rem', 
                    fontWeight: '600',
                    color: '#666',
                    textTransform: 'uppercase',
                    marginBottom: '0.5rem',
                    letterSpacing: '0.5px'
                  }}>
                    Quality Assessment
                  </div>
                  <p style={{ 
                    fontSize: '1.4rem', 
                    fontWeight: '600', 
                    color: explanation.grade === 'A' ? 'var(--accent)' : 
                          explanation.grade === 'C' ? '#c0392b' : 'var(--text)',
                    margin: '0 0 0.75rem 0'
                  }}>
                    Grade {explanation.grade}
                  </p>
                  <div style={{ marginTop: '0.5rem' }}>
                    <ScoreBar label="Color" value={explanation.color_score} />
                    <ScoreBar label="Size" value={explanation.size_score} />
                    <ScoreBar label="Ripeness" value={explanation.ripeness_score} />
                  </div>

                  {overrideState === 'idle' && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setOverrideState('editing')}
                      style={{ marginTop: '1rem' }}
                    >
                      Disagree with this grade?
                    </button>
                  )}
                  {overrideState === 'editing' && (
                    <div className="override-panel">
                      <select
                        value={correctedGrade}
                        onChange={e => setCorrectedGrade(e.target.value)}
                      >
                        <option value="">Corrected grade...</option>
                        <option value="A">Grade A</option>
                        <option value="B">Grade B</option>
                        <option value="C">Grade C</option>
                      </select>
                      <button
                        className="btn btn-sm"
                        onClick={handleOverride}
                        disabled={!correctedGrade || overrideSubmitting}
                      >
                        {overrideSubmitting ? 'Submitting...' : 'Submit'}
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => { setOverrideState('idle'); setCorrectedGrade('') }}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                  {overrideState === 'done' && (
                    <p className="override-confirm" style={{ marginTop: '1rem' }}>
                      Correction recorded.
                    </p>
                  )}
                </div>
              )}
              
              <div className="card">
                <div style={{ 
                  fontSize: '0.75rem', 
                  fontWeight: '600',
                  color: '#666',
                  textTransform: 'uppercase',
                  marginBottom: '0.5rem',
                  letterSpacing: '0.5px'
                }}>
                  Analysis Layer
                </div>
                <p style={{ 
                  fontSize: '0.95rem', 
                  color: 'var(--muted)',
                  margin: 0
                }}>
                  {explanation.layer_used}
                </p>
              </div>
            </div>
 
            {/* Explanation */}
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <h2 style={{ 
                fontSize: '1.1rem', 
                fontWeight: '600', 
                marginBottom: '0.75rem',
                color: 'var(--text)'
              }}>
                Explanation
              </h2>
              <p style={{ color: 'var(--muted)', margin: 0 }}>
                {explanation.explanation}
              </p>
            </div>
 
            {/* Heatmap */}
            {explanation.heatmap_base64 && (
              <div className="card">
                <h2 style={{ 
                  fontSize: '1.1rem', 
                  fontWeight: '600', 
                  marginBottom: '0.5rem',
                  color: 'var(--text)'
                }}>
                  Visual Analysis (Grad-CAM)
                </h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '1rem' }}>
                  Highlighted areas show regions that influenced the quality assessment
                </p>
                <div style={{ textAlign: 'center' }}>
                  <img 
                    src={`data:image/png;base64,${explanation.heatmap_base64}`} 
                    alt="Heatmap"
                    style={{ 
                      maxHeight: '500px',
                      maxWidth: '100%',
                      borderRadius: 'var(--radius)'
                    }}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
 
export default App