const { useState, useEffect } = React;

function HealthBanner() {
    const [health, setHealth] = useState(null);

    useEffect(() => {
        fetch("/api/health")
            .then(r => r.json())
            .then(setHealth)
            .catch(() => setHealth({ status: "unknown" }));
    }, []);

    if (!health) return null;

    const colors = { healthy: "#2ecc71", degraded: "#f39c12", unknown: "#95a5a6" };
    const labels = { healthy: "Feed Healthy", degraded: "Feed Degraded (>24h)", unknown: "Feed Status Unknown" };

    return (
        <div className="health-banner" style={{ backgroundColor: colors[health.status] || "#95a5a6" }}>
            <span>{labels[health.status] || "Unknown"}</span>
            {health.last_success_at && (
                <span className="health-detail">
                    Last success: {new Date(health.last_success_at).toLocaleString()}
                </span>
            )}
            {health.consecutive_failures > 0 && (
                <span className="health-detail">
                    Failures: {health.consecutive_failures}
                </span>
            )}
        </div>
    );
}

function RatingBadge({ label, value, max }) {
    if (value === null || value === undefined) return <span className="rating na">{label}: N/A</span>;

    let color = "rating-red";
    if (max === 10) {
        if (value >= 7) color = "rating-green";
        else if (value >= 5) color = "rating-yellow";
    } else {
        if (value >= 70) color = "rating-green";
        else if (value >= 50) color = "rating-yellow";
    }

    return <span className={`rating ${color}`}>{label}: {value}{max === 100 ? "%" : ""}</span>;
}

function MovieCard({ movie, onMarkRead, onEnrich }) {
    const [loading, setLoading] = useState(false);
    const [enriching, setEnriching] = useState(false);

    const handleMarkRead = async () => {
        setLoading(true);
        try {
            await fetch(`/api/movies/${movie.id}/read`, { method: "POST" });
            onMarkRead(movie.id);
        } catch (e) {
            console.error("Failed to mark as read:", e);
        }
        setLoading(false);
    };

    const handleEnrich = async () => {
        setEnriching(true);
        try {
            const res = await fetch(`/api/movies/${movie.id}/enrich`, { method: "POST" });
            const data = await res.json();
            onEnrich(movie.id, data);
        } catch (e) {
            console.error("Failed to enrich:", e);
        }
        setEnriching(false);
    };

    return (
        <div className="movie-card">
            {movie.poster_url && (
                <div className="movie-poster">
                    <img src={movie.poster_url} alt={movie.title} />
                </div>
            )}
            <div className="movie-info">
                <h3 className="movie-title">{movie.title} <span className="movie-year">({movie.year})</span></h3>

                <div className="movie-genres">
                    {movie.genres.map((g, i) => (
                        <span key={i} className="badge genre-badge">{g}</span>
                    ))}
                </div>

                <div className="movie-qualities">
                    {movie.qualities.map((q, i) => (
                        <span key={i} className="badge quality-badge">{q}</span>
                    ))}
                </div>

                <div className="movie-ratings">
                    <RatingBadge label="IMDb" value={movie.imdb_rating} max={10} />
                    <RatingBadge label="RT" value={movie.rt_expert_rating} max={100} />
                    <RatingBadge label="Audience" value={movie.rt_audience_rating} max={100} />
                </div>

                {movie.enrichment_error && (
                    <p className="enrichment-error">{movie.enrichment_error}</p>
                )}

                <div className="movie-actions">
                    <button
                        className="btn btn-read"
                        onClick={handleMarkRead}
                        disabled={loading}
                    >
                        {loading ? "..." : "Mark as Read"}
                    </button>
                    <button
                        className="btn btn-enrich"
                        onClick={handleEnrich}
                        disabled={enriching}
                    >
                        {enriching ? "Loading..." : "Refresh Ratings"}
                    </button>
                </div>
            </div>
        </div>
    );
}

function App() {
    const [sections, setSections] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchMovies = () => {
        setLoading(true);
        fetch("/api/movies")
            .then(r => r.json())
            .then(data => {
                setSections(data.sections);
                setTotalCount(data.total_count);
                setLoading(false);
            })
            .catch(e => {
                setError("Failed to load movies");
                setLoading(false);
            });
    };

    useEffect(fetchMovies, []);

    const handleMarkRead = (movieId) => {
        setSections(prev =>
            prev.map(section => ({
                ...section,
                movies: section.movies.filter(m => m.id !== movieId)
            })).filter(section => section.movies.length > 0)
        );
        setTotalCount(prev => prev - 1);
    };

    const handleEnrich = (movieId, enrichData) => {
        setSections(prev =>
            prev.map(section => ({
                ...section,
                movies: section.movies.map(m =>
                    m.id === movieId
                        ? { ...m, ...enrichData }
                        : m
                )
            }))
        );
    };

    if (loading) return <div className="loading">Loading movies...</div>;
    if (error) return <div className="error">{error}</div>;

    return (
        <div className="app">
            <header className="app-header">
                <h1>pelis-feed</h1>
                <span className="movie-count">{totalCount} movies</span>
            </header>

            <HealthBanner />

            {sections.length === 0 ? (
                <div className="empty-state">
                    <p>No movies to display. Run the ingester first:</p>
                    <code>python src/cli/main.py</code>
                </div>
            ) : (
                sections.map((section, i) => (
                    <section key={i} className="year-section">
                        <h2 className="year-header">{section.label}</h2>
                        <div className="movie-grid">
                            {section.movies.map(movie => (
                                <MovieCard
                                    key={movie.id}
                                    movie={movie}
                                    onMarkRead={handleMarkRead}
                                    onEnrich={handleEnrich}
                                />
                            ))}
                        </div>
                    </section>
                ))
            )}
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
