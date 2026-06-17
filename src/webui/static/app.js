const { useState, useEffect } = React;

// ---------------------------------------------------------------------------
// Shared utilities
// ---------------------------------------------------------------------------

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

function Badge({ children, className = "" }) {
    return <span className={`badge ${className}`}>{children}</span>;
}

// ---------------------------------------------------------------------------
// Health banner — shows status for all feeds
// ---------------------------------------------------------------------------

function HealthBanner() {
    const [feeds, setFeeds] = useState([]);

    useEffect(() => {
        fetch("/api/health")
            .then(r => r.json())
            .then(data => setFeeds(data.feeds || []))
            .catch(() => setFeeds([]));
    }, []);

    if (feeds.length === 0) return null;

    const degraded = feeds.filter(f => f.status === "degraded");
    const unknown = feeds.filter(f => f.status === "unknown");
    const overallStatus = degraded.length > 0 ? "degraded" : unknown.length === feeds.length ? "unknown" : "healthy";

    const colors = { healthy: "#2ecc71", degraded: "#f39c12", unknown: "#95a5a6" };
    const labels = { healthy: "All Feeds Healthy", degraded: `${degraded.length} Feed(s) Degraded`, unknown: "Feed Status Unknown" };

    return (
        <div className="health-banner" style={{ backgroundColor: colors[overallStatus] }}>
            <span>{labels[overallStatus]}</span>
            {degraded.map(f => (
                <span key={f.feed_name} className="health-detail">{f.feed_name}: down &gt;24h</span>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Movies tab
// ---------------------------------------------------------------------------

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
                    {movie.genres.map((g, i) => <Badge key={i} className="genre-badge">{g}</Badge>)}
                </div>
                <div className="movie-qualities">
                    {movie.qualities.map((q, i) => <Badge key={i} className="quality-badge">{q}</Badge>)}
                </div>
                <div className="movie-ratings">
                    <RatingBadge label="IMDb" value={movie.imdb_rating} max={10} />
                    <RatingBadge label="RT" value={movie.rt_expert_rating} max={100} />
                    <RatingBadge label="Audience" value={movie.rt_audience_rating} max={100} />
                </div>
                {movie.enrichment_error && <p className="enrichment-error">{movie.enrichment_error}</p>}
                <div className="movie-actions">
                    <button className="btn btn-read" onClick={handleMarkRead} disabled={loading}>
                        {loading ? "..." : "Mark as Read"}
                    </button>
                    <button className="btn btn-enrich" onClick={handleEnrich} disabled={enriching}>
                        {enriching ? "Loading..." : "Refresh Ratings"}
                    </button>
                </div>
            </div>
        </div>
    );
}

function MoviesTab() {
    const [sections, setSections] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchMovies = () => {
        setLoading(true);
        fetch("/api/movies")
            .then(r => r.json())
            .then(data => { setSections(data.sections); setTotalCount(data.total_count); setLoading(false); })
            .catch(() => { setError("Failed to load movies"); setLoading(false); });
    };

    useEffect(fetchMovies, []);

    const handleMarkRead = (movieId) => {
        setSections(prev =>
            prev.map(s => ({ ...s, movies: s.movies.filter(m => m.id !== movieId) }))
                .filter(s => s.movies.length > 0)
        );
        setTotalCount(prev => prev - 1);
    };

    const handleEnrich = (movieId, enrichData) => {
        setSections(prev =>
            prev.map(s => ({ ...s, movies: s.movies.map(m => m.id === movieId ? { ...m, ...enrichData } : m) }))
        );
    };

    if (loading) return <div className="loading">Loading movies...</div>;
    if (error) return <div className="error">{error}</div>;

    return (
        <div>
            <div className="tab-count">{totalCount} movies</div>
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
                                <MovieCard key={movie.id} movie={movie} onMarkRead={handleMarkRead} onEnrich={handleEnrich} />
                            ))}
                        </div>
                    </section>
                ))
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// News tab — shared components
// ---------------------------------------------------------------------------

function NewsItemRow({ item, onToggleRead }) {
    const [loading, setLoading] = useState(false);

    const handleToggle = async () => {
        setLoading(true);
        const action = item.is_read ? "unread" : "read";
        try {
            await fetch(`/api/news/items/${item.id}/${action}`, { method: "POST" });
            onToggleRead(item.id, !item.is_read);
        } catch (e) {
            console.error("Failed to toggle read:", e);
        }
        setLoading(false);
    };

    return (
        <div className={`news-item ${item.is_read ? "news-item-read" : ""}`}>
            <div className="news-item-header">
                <a className="news-item-title" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                {item.matched_filter_name && (
                    <Badge className="filter-badge">{item.matched_filter_name}</Badge>
                )}
            </div>
            {item.published_at && (
                <div className="news-item-date">{new Date(item.published_at).toLocaleString()}</div>
            )}
            <button className="btn btn-read btn-sm" onClick={handleToggle} disabled={loading}>
                {loading ? "..." : item.is_read ? "Mark Unread" : "Mark Read"}
            </button>
        </div>
    );
}

function AIViewRow({ item, onToggleRead, onToggleKeep }) {
    const [readLoading, setReadLoading] = useState(false);
    const [keepLoading, setKeepLoading] = useState(false);

    const handleToggleRead = async () => {
        setReadLoading(true);
        const action = item.is_read ? "unread" : "read";
        try {
            await fetch(`/api/news/views/${item.id}/${action}`, { method: "POST" });
            onToggleRead(item.id, !item.is_read);
        } catch (e) {
            console.error("Failed to toggle read:", e);
        }
        setReadLoading(false);
    };

    const handleToggleKeep = async () => {
        setKeepLoading(true);
        const action = item.keep_as_context ? "unkeep" : "keep";
        try {
            await fetch(`/api/news/views/${item.id}/${action}`, { method: "POST" });
            onToggleKeep(item.id, !item.keep_as_context);
        } catch (e) {
            console.error("Failed to toggle keep:", e);
        }
        setKeepLoading(false);
    };

    return (
        <div className={`news-item ai-view-item ${item.is_read ? "news-item-read" : ""}`}>
            <div className="news-item-header">
                <a className="news-item-title" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                {item.category && <Badge className="category-badge">{item.category}</Badge>}
                {item.keep_as_context && <Badge className="context-badge">Context</Badge>}
            </div>
            {item.published_at && (
                <div className="news-item-date">{new Date(item.published_at).toLocaleString()}</div>
            )}
            {item.summary && <p className="ai-summary">{item.summary}</p>}
            {item.tags && item.tags.length > 0 && (
                <div className="ai-tags">
                    {item.tags.map((t, i) => <Badge key={i} className="tag-badge">#{t}</Badge>)}
                </div>
            )}
            <div className="news-item-actions">
                <button className="btn btn-read btn-sm" onClick={handleToggleRead} disabled={readLoading}>
                    {readLoading ? "..." : item.is_read ? "Mark Unread" : "Mark Read"}
                </button>
                <button
                    className={`btn btn-sm ${item.keep_as_context ? "btn-keep-active" : "btn-keep"}`}
                    onClick={handleToggleKeep}
                    disabled={keepLoading}
                    title="Keep as context for future AI filtering runs"
                >
                    {keepLoading ? "..." : item.keep_as_context ? "Unkeep" : "Keep as Context"}
                </button>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// News feed views
// ---------------------------------------------------------------------------

function UnfilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    }, [feedName]);

    const handleToggleRead = (id, isRead) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, is_read: isRead } : item));
    };

    if (loading) return <div className="loading">Loading...</div>;
    if (items.length === 0) return <div className="empty-state">No items yet.</div>;

    return (
        <div className="news-list">
            {items.map(item => (
                <NewsItemRow key={item.id} item={item} onToggleRead={handleToggleRead} />
            ))}
        </div>
    );
}

function FilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    }, [feedName]);

    const handleToggleRead = (id, isRead) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, is_read: isRead } : item));
    };

    if (loading) return <div className="loading">Loading...</div>;
    if (items.length === 0) return <div className="empty-state">No matched items yet.</div>;

    return (
        <div className="news-list">
            {items.map(item => (
                <NewsItemRow key={item.id} item={item} onToggleRead={handleToggleRead} />
            ))}
        </div>
    );
}

function AIFilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showRaw, setShowRaw] = useState(false);
    const [rawItems, setRawItems] = useState([]);
    const [rawLoading, setRawLoading] = useState(false);

    useEffect(() => {
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    }, [feedName]);

    const handleShowRaw = () => {
        if (!showRaw && rawItems.length === 0) {
            setRawLoading(true);
            fetch(`/api/news/${encodeURIComponent(feedName)}/raw`)
                .then(r => r.json())
                .then(data => { setRawItems(data.items || []); setRawLoading(false); })
                .catch(() => setRawLoading(false));
        }
        setShowRaw(prev => !prev);
    };

    const handleToggleRead = (id, isRead) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, is_read: isRead } : item));
    };

    const handleToggleKeep = (id, keepAsContext) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, keep_as_context: keepAsContext } : item));
    };

    if (loading) return <div className="loading">Loading...</div>;

    return (
        <div>
            <div className="ai-feed-toolbar">
                <button className="btn btn-secondary btn-sm" onClick={handleShowRaw}>
                    {showRaw ? "Hide Raw Items" : "Show Raw Items"}
                </button>
            </div>

            {showRaw ? (
                rawLoading ? (
                    <div className="loading">Loading raw items...</div>
                ) : rawItems.length === 0 ? (
                    <div className="empty-state">No raw items.</div>
                ) : (
                    <div className="news-list">
                        {rawItems.map(item => (
                            <div key={item.id} className={`news-item ${item.is_read ? "news-item-read" : ""}`}>
                                <div className="news-item-header">
                                    <a className="news-item-title" href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                                    {item.has_ai_view && <Badge className="processed-badge">Processed</Badge>}
                                </div>
                                {item.published_at && (
                                    <div className="news-item-date">{new Date(item.published_at).toLocaleString()}</div>
                                )}
                            </div>
                        ))}
                    </div>
                )
            ) : items.length === 0 ? (
                <div className="empty-state">No AI-filtered items yet. Run the filter processor first:<br /><code>python src/cli/filter.py</code></div>
            ) : (
                <div className="news-list">
                    {items.map(item => (
                        <AIViewRow key={item.id} item={item} onToggleRead={handleToggleRead} onToggleKeep={handleToggleKeep} />
                    ))}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// News tab — feed list + active feed view
// ---------------------------------------------------------------------------

function NewsTab() {
    const [feeds, setFeeds] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeFeed, setActiveFeed] = useState(null);

    useEffect(() => {
        fetch("/api/news")
            .then(r => r.json())
            .then(data => {
                const feedList = data.feeds || [];
                setFeeds(feedList);
                if (feedList.length > 0 && !activeFeed) setActiveFeed(feedList[0].name);
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    if (loading) return <div className="loading">Loading news feeds...</div>;
    if (feeds.length === 0) return (
        <div className="empty-state">
            <p>No news feeds configured. Add <code>news_feeds</code> to your config.yaml.</p>
        </div>
    );

    const currentFeed = feeds.find(f => f.name === activeFeed);

    return (
        <div className="news-tab">
            <div className="news-feed-nav">
                {feeds.map(feed => (
                    <button
                        key={feed.name}
                        className={`feed-nav-btn ${activeFeed === feed.name ? "active" : ""}`}
                        onClick={() => setActiveFeed(feed.name)}
                    >
                        {feed.name}
                        {feed.unread_count > 0 && (
                            <span className="unread-badge">{feed.unread_count}</span>
                        )}
                    </button>
                ))}
            </div>

            {currentFeed && (
                <div className="news-feed-content">
                    <div className="feed-type-label">{currentFeed.type}</div>
                    {currentFeed.type === "unfiltered" && <UnfilteredFeedView feedName={currentFeed.name} />}
                    {currentFeed.type === "filtered" && <FilteredFeedView feedName={currentFeed.name} />}
                    {currentFeed.type === "ai_filtered" && <AIFilteredFeedView feedName={currentFeed.name} />}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Root app with tab navigation
// ---------------------------------------------------------------------------

function App() {
    const [activeTab, setActiveTab] = useState("movies");

    return (
        <div className="app">
            <header className="app-header">
                <h1>pelis-feed</h1>
                <nav className="tab-nav">
                    <button
                        className={`tab-btn ${activeTab === "movies" ? "active" : ""}`}
                        onClick={() => setActiveTab("movies")}
                    >
                        Movies
                    </button>
                    <button
                        className={`tab-btn ${activeTab === "news" ? "active" : ""}`}
                        onClick={() => setActiveTab("news")}
                    >
                        News
                    </button>
                </nav>
            </header>

            <HealthBanner />

            <main className="tab-content">
                {activeTab === "movies" && <MoviesTab />}
                {activeTab === "news" && <NewsTab />}
            </main>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
