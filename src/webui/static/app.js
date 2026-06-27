const { useState, useEffect } = React;
const html = htm.bind(React.createElement);

// ---------------------------------------------------------------------------
// Shared utilities
// ---------------------------------------------------------------------------

function RatingBadge({ label, value, max, href }) {
    if (value === null || value === undefined) return html`<span className="rating na">${label}: N/A</span>`;
    let color = "rating-red";
    if (max === 10) {
        if (value >= 7) color = "rating-green";
        else if (value >= 5) color = "rating-yellow";
    } else {
        if (value >= 70) color = "rating-green";
        else if (value >= 50) color = "rating-yellow";
    }
    const badge = html`<span className=${`rating ${color}`}>${label}: ${value}${max === 100 ? "%" : ""}</span>`;
    if (!href) return badge;
    return html`<a href=${href} target="_blank" rel="noreferrer" className="rating-link">${badge}</a>`;
}

function Badge({ children, className = "" }) {
    return html`<span className=${`badge ${className}`}>${children}</span>`;
}

// ---------------------------------------------------------------------------
// Shared news toolbar — export / import / mark-all-read
// ---------------------------------------------------------------------------

function FeedToolbar({ feedName, onMarkAllRead, markingAll, onImportDone }) {
    const [importing, setImporting] = useState(false);
    const [importResult, setImportResult] = useState(null);

    const handleExport = () => {
        window.location.href = `/api/news/${encodeURIComponent(feedName)}/export`;
    };

    const handleImport = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setImporting(true);
        setImportResult(null);
        try {
            const text = await file.text();
            const payload = JSON.parse(text);
            const res = await fetch(`/api/news/${encodeURIComponent(feedName)}/import`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Import failed");
            setImportResult({ ok: true, message: `Imported ${data.imported} items${data.discarded ? `, ${data.discarded} discarded` : ""}.` });
            if (onImportDone) onImportDone();
        } catch (err) {
            setImportResult({ ok: false, message: err.message });
        }
        setImporting(false);
        e.target.value = "";
    };

    return html`
        <div>
            <div className="ai-feed-toolbar">
                <button className="btn btn-secondary btn-sm" onClick=${handleExport}>Export Unread</button>
                <label className=${`btn btn-secondary btn-sm ${importing ? "btn-disabled" : ""}`}>
                    ${importing ? "Importing…" : "Import Results"}
                    <input type="file" accept=".json" style=${{ display: "none" }} onChange=${handleImport} disabled=${importing} />
                </label>
                <button className="btn btn-secondary btn-sm" onClick=${onMarkAllRead} disabled=${markingAll}>
                    ${markingAll ? "..." : "Mark All Read"}
                </button>
            </div>
            ${importResult && html`
                <div className=${`import-result ${importResult.ok ? "import-ok" : "import-error"}`}>
                    ${importResult.message}
                </div>
            `}
        </div>
    `;
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

    return html`
        <div className="health-banner" style=${{ backgroundColor: colors[overallStatus] }}>
            <span>${labels[overallStatus]}</span>
            ${degraded.map(f => html`<span key=${f.feed_name} className="health-detail">${f.feed_name}: down >24h</span>`)}
        </div>
    `;
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

    return html`
        <div className="movie-card">
            ${movie.poster_url && html`
                <div className="movie-poster">
                    <img src=${movie.poster_url} alt=${movie.title} />
                </div>
            `}
            <div className="movie-info">
                <h3 className="movie-title">${movie.title} <span className="movie-year">(${movie.year})</span></h3>
                <div className="movie-genres">
                    ${movie.genres.map((g, i) => html`<${Badge} key=${i} className="genre-badge">${g}</${Badge}>`)}
                </div>
                <div className="movie-qualities">
                    ${movie.qualities.map((q, i) => html`
                        <a key=${i} href=${movie.torrent_url} target="_blank" rel="noreferrer" className="quality-link">
                            <${Badge} className="quality-badge">${q}</${Badge}>
                        </a>
                    `)}
                </div>
                <div className="movie-ratings">
                    <${RatingBadge} label="IMDb" value=${movie.imdb_rating} max=${10}
                        href=${movie.imdb_id
                            ? `https://www.imdb.com/title/${movie.imdb_id}/`
                            : (movie.imdb_rating != null ? `https://www.imdb.com/find/?q=${encodeURIComponent(movie.title + " " + movie.year)}&s=tt&ttype=ft` : null)} />
                    <${RatingBadge} label="RT" value=${movie.rt_expert_rating} max=${100}
                        href=${movie.rt_expert_rating != null ? `https://www.rottentomatoes.com/search/?search=${encodeURIComponent(movie.title)}` : null} />
                    <${RatingBadge} label="Audience" value=${movie.rt_audience_rating} max=${100}
                        href=${movie.rt_audience_rating != null ? `https://www.rottentomatoes.com/search/?search=${encodeURIComponent(movie.title)}` : null} />
                </div>
                ${movie.enrichment_error && html`<p className="enrichment-error">${movie.enrichment_error}</p>`}
                <div className="movie-actions">
                    <button className="btn btn-read" onClick=${handleMarkRead} disabled=${loading}>
                        ${loading ? "..." : "Mark as Read"}
                    </button>
                    <button className="btn btn-enrich" onClick=${handleEnrich} disabled=${enriching}>
                        ${enriching ? "Loading..." : "Refresh Ratings"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

function MoviesTab() {
    const [sections, setSections] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isFiltered, setIsFiltered] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const fetchMovies = (filtered) => {
        setLoading(true);
        fetch(`/api/movies?filtered=${filtered}`)
            .then(r => r.json())
            .then(data => { setSections(data.sections); setTotalCount(data.total_count); setLoading(false); })
            .catch(() => { setError("Failed to load movies"); setLoading(false); });
    };

    useEffect(() => fetchMovies(isFiltered), []);

    const handleToggleView = (filtered) => {
        if (filtered === isFiltered) return;
        setIsFiltered(filtered);
        fetchMovies(filtered);
    };

    const handleMarkRead = (movieId) => {
        setSections(prev =>
            prev.map(s => ({ ...s, movies: s.movies.filter(m => m.id !== movieId) }))
                .filter(s => s.movies.length > 0)
        );
        setTotalCount(prev => prev - 1);
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch("/api/movies/read-all", { method: "POST" });
            setSections([]);
            setTotalCount(0);
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    const handleEnrich = (movieId, enrichData) => {
        setSections(prev =>
            prev.map(s => ({ ...s, movies: s.movies.map(m => m.id === movieId ? { ...m, ...enrichData } : m) }))
        );
    };

    if (error) return html`<div className="error">${error}</div>`;

    return html`
        <div>
            <div className="movies-toolbar">
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${isFiltered ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => handleToggleView(true)}>Filtered</button>
                    <button className=${`btn btn-sm ${!isFiltered ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => handleToggleView(false)}>All</button>
                </div>
                <div className="tab-count">${totalCount} movies</div>
                <button className="btn btn-secondary btn-sm" onClick=${handleMarkAllRead} disabled=${markingAll}>
                    ${markingAll ? "..." : "Mark All Read"}
                </button>
            </div>
            ${loading
                ? html`<div className="loading">Loading movies...</div>`
                : sections.length === 0
                    ? html`<div className="empty-state">
                        <p>No movies to display. Run the ingester first:</p>
                        <code>python src/cli/main.py</code>
                    </div>`
                    : sections.map((section, i) => html`
                        <section key=${i} className="year-section">
                            <h2 className="year-header">${section.label}</h2>
                            <div className="movie-grid">
                                ${section.movies.map(movie => html`
                                    <${MovieCard} key=${movie.id} movie=${movie} onMarkRead=${handleMarkRead} onEnrich=${handleEnrich} />
                                `)}
                            </div>
                        </section>
                    `)
            }
        </div>
    `;
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

    return html`
        <div className=${`news-item ${item.is_read ? "news-item-read" : ""}`}>
            <div className="news-item-header">
                <a className="news-item-title" href=${item.url} target="_blank" rel="noreferrer">${item.title}</a>
                ${item.matched_filter_name && html`<${Badge} className="filter-badge">${item.matched_filter_name}</${Badge}>`}
            </div>
            ${item.published_at && html`<div className="news-item-date">${new Date(item.published_at).toLocaleString()}</div>`}
            <button className="btn btn-read btn-sm" onClick=${handleToggle} disabled=${loading}>
                ${loading ? "..." : item.is_read ? "Mark Unread" : "Mark Read"}
            </button>
        </div>
    `;
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

    return html`
        <div className=${`news-item ai-view-item ${item.is_read ? "news-item-read" : ""}`}>
            <div className="news-item-header">
                <a className="news-item-title" href=${item.url} target="_blank" rel="noreferrer">${item.title}</a>
                ${item.category && html`<${Badge} className="category-badge">${item.category}</${Badge}>`}
                ${item.keep_as_context && html`<${Badge} className="context-badge">Context</${Badge}>`}
            </div>
            ${item.published_at && html`<div className="news-item-date">${new Date(item.published_at).toLocaleString()}</div>`}
            ${item.summary && html`<p className="ai-summary">${item.summary}</p>`}
            ${item.tags && item.tags.length > 0 && html`
                <div className="ai-tags">
                    ${item.tags.map((t, i) => html`<${Badge} key=${i} className="tag-badge">#${t}</${Badge}>`)}
                </div>
            `}
            <div className="news-item-actions">
                <button className="btn btn-read btn-sm" onClick=${handleToggleRead} disabled=${readLoading}>
                    ${readLoading ? "..." : item.is_read ? "Mark Unread" : "Mark Read"}
                </button>
                <button
                    className=${`btn btn-sm ${item.keep_as_context ? "btn-keep-active" : "btn-keep"}`}
                    onClick=${handleToggleKeep}
                    disabled=${keepLoading}
                    title="Keep as context for future AI filtering runs"
                >
                    ${keepLoading ? "..." : item.keep_as_context ? "Unkeep" : "Keep as Context"}
                </button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// News feed views
// ---------------------------------------------------------------------------

function UnfilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const loadItems = () => {
        setLoading(true);
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    };

    useEffect(() => { loadItems(); }, [feedName]);

    const handleToggleRead = (id, isRead) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, is_read: isRead } : item));
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/news/${encodeURIComponent(feedName)}/read-all`, { method: "POST" });
            setItems(prev => prev.map(item => ({ ...item, is_read: true })));
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    if (loading) return html`<div className="loading">Loading...</div>`;

    return html`
        <div>
            <${FeedToolbar} feedName=${feedName} onMarkAllRead=${handleMarkAllRead} markingAll=${markingAll} onImportDone=${loadItems} />
            ${items.length === 0
                ? html`<div className="empty-state">No items yet.</div>`
                : html`<div className="news-list">
                    ${items.map(item => html`<${NewsItemRow} key=${item.id} item=${item} onToggleRead=${handleToggleRead} />`)}
                </div>`
            }
        </div>
    `;
}

function FilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const loadItems = () => {
        setLoading(true);
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    };

    useEffect(() => { loadItems(); }, [feedName]);

    const handleToggleRead = (id, isRead) => {
        setItems(prev => prev.map(item => item.id === id ? { ...item, is_read: isRead } : item));
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/news/${encodeURIComponent(feedName)}/read-all`, { method: "POST" });
            setItems(prev => prev.map(item => ({ ...item, is_read: true })));
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    if (loading) return html`<div className="loading">Loading...</div>`;

    return html`
        <div>
            <${FeedToolbar} feedName=${feedName} onMarkAllRead=${handleMarkAllRead} markingAll=${markingAll} onImportDone=${loadItems} />
            ${items.length === 0
                ? html`<div className="empty-state">No matched items yet.</div>`
                : html`<div className="news-list">
                    ${items.map(item => html`<${NewsItemRow} key=${item.id} item=${item} onToggleRead=${handleToggleRead} />`)}
                </div>`
            }
        </div>
    `;
}

function AIFilteredFeedView({ feedName }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showRaw, setShowRaw] = useState(false);
    const [rawItems, setRawItems] = useState([]);
    const [rawLoading, setRawLoading] = useState(false);
    const [markingAll, setMarkingAll] = useState(false);

    const loadItems = () => {
        fetch(`/api/news/${encodeURIComponent(feedName)}/items`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    };

    useEffect(() => { loadItems(); }, [feedName]);

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

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/news/${encodeURIComponent(feedName)}/read-all`, { method: "POST" });
            setItems(prev => prev.map(item => ({ ...item, is_read: true })));
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    if (loading) return html`<div className="loading">Loading...</div>`;

    const rawView = showRaw
        ? (rawLoading
            ? html`<div className="loading">Loading raw items...</div>`
            : rawItems.length === 0
                ? html`<div className="empty-state">No raw items.</div>`
                : html`<div className="news-list">
                    ${rawItems.map(item => html`
                        <div key=${item.id} className=${`news-item ${item.is_read ? "news-item-read" : ""}`}>
                            <div className="news-item-header">
                                <a className="news-item-title" href=${item.url} target="_blank" rel="noreferrer">${item.title}</a>
                                ${item.has_ai_view && html`<${Badge} className="processed-badge">Processed</${Badge}>`}
                            </div>
                            ${item.published_at && html`<div className="news-item-date">${new Date(item.published_at).toLocaleString()}</div>`}
                        </div>
                    `)}
                </div>`)
        : (items.length === 0
            ? html`<div className="empty-state">No AI-filtered items yet. Export unread items, process externally, then import the result.</div>`
            : html`<div className="news-list">
                ${items.map(item => html`<${AIViewRow} key=${item.id} item=${item} onToggleRead=${handleToggleRead} onToggleKeep=${handleToggleKeep} />`)}
            </div>`);

    return html`
        <div>
            <${FeedToolbar} feedName=${feedName} onMarkAllRead=${handleMarkAllRead} markingAll=${markingAll} onImportDone=${loadItems} />
            <div className="ai-feed-toolbar">
                <button className="btn btn-secondary btn-sm" onClick=${handleShowRaw}>
                    ${showRaw ? "Hide Raw Items" : "Show Raw Items"}
                </button>
            </div>
            ${rawView}
        </div>
    `;
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

    if (loading) return html`<div className="loading">Loading news feeds...</div>`;
    if (feeds.length === 0) return html`
        <div className="empty-state">
            <p>No news feeds configured. Add <code>news_feeds</code> to your config.yaml.</p>
        </div>
    `;

    const currentFeed = feeds.find(f => f.name === activeFeed);

    return html`
        <div className="news-tab">
            <div className="news-feed-nav">
                ${feeds.map(feed => html`
                    <button
                        key=${feed.name}
                        className=${`feed-nav-btn ${activeFeed === feed.name ? "active" : ""}`}
                        onClick=${() => setActiveFeed(feed.name)}
                    >
                        ${feed.name}
                        ${feed.unread_count > 0 && html`<span className="unread-badge">${feed.unread_count}</span>`}
                    </button>
                `)}
            </div>
            ${currentFeed && html`
                <div className="news-feed-content">
                    <div className="feed-type-label">${currentFeed.type}</div>
                    ${currentFeed.type === "unfiltered" && html`<${UnfilteredFeedView} key=${currentFeed.name} feedName=${currentFeed.name} />`}
                    ${currentFeed.type === "filtered" && html`<${FilteredFeedView} key=${currentFeed.name} feedName=${currentFeed.name} />`}
                    ${currentFeed.type === "ai_filtered" && html`<${AIFilteredFeedView} key=${currentFeed.name} feedName=${currentFeed.name} />`}
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Series tab
// ---------------------------------------------------------------------------

function SeriesTab() {
    const [view, setView] = useState("unread");
    const [seriesList, setSeriesList] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [markingAll, setMarkingAll] = useState(false);

    const loadSeries = (v) => {
        setLoading(true);
        setError(null);
        fetch(`/api/series?view=${v}`)
            .then(r => r.json())
            .then(data => { setSeriesList(data.series || []); setLoading(false); })
            .catch(() => { setError("Failed to load series"); setLoading(false); });
    };

    useEffect(() => { loadSeries("unread"); }, []);

    const handleViewChange = (v) => {
        if (v === view) return;
        setView(v);
        loadSeries(v);
    };

    const handleMarkRead = (episodeId) => {
        fetch(`/api/series/episodes/${episodeId}/read`, { method: "POST" });
        setSeriesList(prev =>
            prev.map(s => ({
                ...s,
                seasons: s.seasons.map(season => ({
                    ...season,
                    episodes: season.episodes.filter(ep => ep.id !== episodeId),
                })).filter(season => season.episodes.length > 0),
            })).filter(s => s.seasons.length > 0)
        );
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch("/api/series/read-all", { method: "POST" });
            setSeriesList([]);
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    const handleIgnore = async (seriesId) => {
        await fetch(`/api/series/${seriesId}/ignore`, { method: "POST" });
        setSeriesList(prev => prev.filter(s => s.id !== seriesId));
    };

    const handleUnignore = async (seriesId) => {
        await fetch(`/api/series/${seriesId}/unignore`, { method: "POST" });
        setSeriesList(prev => prev.filter(s => s.id !== seriesId));
    };

    if (loading) return html`<div className="loading">Loading series...</div>`;
    if (error) return html`<div className="error">${error}</div>`;

    return html`
        <div className="series-tab">
            <div className="movies-toolbar">
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${view === "unread" ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => handleViewChange("unread")}>Unread</button>
                    <button className=${`btn btn-sm ${view === "all" ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => handleViewChange("all")}>All</button>
                    <button className=${`btn btn-sm ${view === "ignored" ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => handleViewChange("ignored")}>Ignored</button>
                </div>
                <div className="tab-count">${seriesList.length} series</div>
                ${view !== "ignored" && html`
                    <button className="btn btn-secondary btn-sm" onClick=${handleMarkAllRead} disabled=${markingAll}>
                        ${markingAll ? "..." : "Mark All Read"}
                    </button>
                `}
            </div>
            ${seriesList.length === 0
                ? html`<div className="empty-state">
                    ${view === "ignored"
                        ? "No ignored series."
                        : html`<p>No series to display. Run the ingester first:</p><code>python src/cli/main.py</code>`}
                </div>`
                : seriesList.map(series => html`
                    <div key=${series.id} className="series-block">
                        <h2 className="series-title">
                            <a href=${series.imdb_url} target="_blank" rel="noreferrer">${series.title}</a>
                            ${view === "ignored"
                                ? html`<button className="btn btn-secondary btn-sm series-ignore-btn" onClick=${() => handleUnignore(series.id)}>Unignore</button>`
                                : html`<button className="btn btn-secondary btn-sm series-ignore-btn" onClick=${() => handleIgnore(series.id)}>Ignore</button>`
                            }
                        </h2>
                        ${series.seasons.map(season => html`
                            <div key=${season.season} className="season-block">
                                <h3 className="season-header">Season ${season.season}</h3>
                                <div className="episode-list">
                                    ${season.episodes.map(ep => html`
                                        <div key=${ep.id} className="episode-row">
                                            <span className="episode-label">E${String(ep.episode).padStart(2, "0")}</span>
                                            <div className="episode-qualities">
                                                ${ep.qualities.map((q, i) => html`
                                                    <a key=${i} href=${q.torrent_page_url} target="_blank" rel="noreferrer" className="quality-link">
                                                        <${Badge} className="quality-badge">${q.quality}</${Badge}>
                                                    </a>
                                                `)}
                                            </div>
                                            ${ep.feed_entry_date && html`
                                                <span className="episode-date">${new Date(ep.feed_entry_date).toLocaleDateString()}</span>
                                            `}
                                            ${view !== "ignored" && html`
                                                <button className="btn btn-read btn-sm" onClick=${() => handleMarkRead(ep.id)}>
                                                    Mark Read
                                                </button>
                                            `}
                                        </div>
                                    `)}
                                </div>
                            </div>
                        `)}
                    </div>
                `)
            }
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Root app with tab navigation
// ---------------------------------------------------------------------------

function App() {
    const [activeTab, setActiveTab] = useState("movies");

    return html`
        <div className="app">
            <header className="app-header">
                <h1>pelis-feed</h1>
                <nav className="tab-nav">
                    <button
                        className=${`tab-btn ${activeTab === "movies" ? "active" : ""}`}
                        onClick=${() => setActiveTab("movies")}
                    >
                        Movies
                    </button>
                    <button
                        className=${`tab-btn ${activeTab === "series" ? "active" : ""}`}
                        onClick=${() => setActiveTab("series")}
                    >
                        Series
                    </button>
                    <button
                        className=${`tab-btn ${activeTab === "news" ? "active" : ""}`}
                        onClick=${() => setActiveTab("news")}
                    >
                        News
                    </button>
                </nav>
            </header>
            <${HealthBanner} />
            <main className="tab-content">
                ${activeTab === "movies" && html`<${MoviesTab} />`}
                ${activeTab === "series" && html`<${SeriesTab} />`}
                ${activeTab === "news" && html`<${NewsTab} />`}
            </main>
        </div>
    `;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(html`<${App} />`);
