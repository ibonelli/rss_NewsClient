const { useState, useEffect } = React;
const html = htm.bind(React.createElement);

// ---------------------------------------------------------------------------
// Client-side router — one URL per feed type (/movies, /series, /news,
// /news/{feed_name}, /design, /design/{feed_name}) using the History API.
// ---------------------------------------------------------------------------

const TABS = ["movies", "series", "news", "design"];

function parseLocation() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    const tab = TABS.includes(parts[0]) ? parts[0] : "movies";
    const feedName = parts.length > 1 ? decodeURIComponent(parts[1]) : null;
    return { tab, feedName };
}

function navigate(path) {
    if (window.location.pathname !== path) {
        window.history.pushState({}, "", path);
        window.dispatchEvent(new Event("pushstate"));
    }
}

function replaceLocation(path) {
    if (window.location.pathname !== path) {
        window.history.replaceState({}, "", path);
        window.dispatchEvent(new Event("pushstate"));
    }
}

function useLocation() {
    const [location, setLocation] = useState(parseLocation());
    useEffect(() => {
        const handler = () => setLocation(parseLocation());
        window.addEventListener("popstate", handler);
        window.addEventListener("pushstate", handler);
        return () => {
            window.removeEventListener("popstate", handler);
            window.removeEventListener("pushstate", handler);
        };
    }, []);
    return location;
}

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

function FeedToolbar({ feedName, onMarkAllRead, markingAll, showMarkAll }) {
    const handleExport = () => {
        window.location.href = `/api/news/${encodeURIComponent(feedName)}/export`;
    };

    return html`
        <div className="ai-feed-toolbar">
            <button className="btn btn-secondary btn-sm" onClick=${handleExport}>Export Unread</button>
            ${showMarkAll && html`
                <button className="btn btn-secondary btn-sm" onClick=${onMarkAllRead} disabled=${markingAll}>
                    ${markingAll ? "..." : "Mark All Read"}
                </button>
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

function MovieCard({ movie, onMarkRead, onMarkUnread, onEnrich }) {
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

    const handleMarkUnread = async () => {
        setLoading(true);
        try {
            await fetch(`/api/movies/${movie.id}/unread`, { method: "POST" });
            onMarkUnread(movie.id);
        } catch (e) {
            console.error("Failed to mark as unread:", e);
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

    const imdbUrl = movie.imdb_id
        ? `https://www.imdb.com/title/${movie.imdb_id}/`
        : `https://www.imdb.com/find/?q=${encodeURIComponent(movie.title + " " + movie.year)}&s=tt&ttype=ft`;

    return html`
        <div className="movie-card">
            ${movie.poster_url && html`
                <div className="movie-poster">
                    <img src=${movie.poster_url} alt=${movie.title} />
                </div>
            `}
            <div className="movie-info">
                <h3 className="movie-title">
                    <a href=${imdbUrl} target="_blank" rel="noreferrer">${movie.title}</a>
                    <span className="movie-year">(${movie.year})</span>
                </h3>
                <div className="movie-body">
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
                        <${RatingBadge} label="IMDb" value=${movie.imdb_rating} max=${10} />
                        <${RatingBadge} label="RT" value=${movie.rt_expert_rating} max=${100}
                            href=${movie.rt_expert_rating != null ? `https://www.rottentomatoes.com/search/?search=${encodeURIComponent(movie.title)}` : null} />
                        <${RatingBadge} label="Audience" value=${movie.rt_audience_rating} max=${100}
                            href=${movie.rt_audience_rating != null ? `https://www.rottentomatoes.com/search/?search=${encodeURIComponent(movie.title)}` : null} />
                    </div>
                    ${movie.enrichment_error && html`<p className="enrichment-error">${movie.enrichment_error}</p>`}
                    <div className="movie-actions">
                        ${onMarkRead && html`
                            <button className="btn btn-read" onClick=${handleMarkRead} disabled=${loading}>
                                ${loading ? "..." : "Mark as Read"}
                            </button>
                        `}
                        ${onMarkUnread && html`
                            <button className="btn btn-secondary btn-sm" onClick=${handleMarkUnread} disabled=${loading}>
                                ${loading ? "..." : "Mark as Unread"}
                            </button>
                        `}
                        <button className="btn btn-enrich" onClick=${handleEnrich} disabled=${enriching}>
                            ${enriching ? "Loading..." : "Refresh Ratings"}
                        </button>
                    </div>
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
    const [isRead, setIsRead] = useState(false);
    const [isFlagged, setIsFlagged] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const fetchMovies = (read, flagged) => {
        setLoading(true);
        fetch(`/api/movies?read=${read}&flagged=${flagged}`)
            .then(r => r.json())
            .then(data => { setSections(data.sections); setTotalCount(data.total_count); setLoading(false); })
            .catch(() => { setError("Failed to load movies"); setLoading(false); });
    };

    useEffect(() => fetchMovies(false, true), []);

    const handleToggleRead = () => {
        const next = !isRead;
        setIsRead(next);
        fetchMovies(next, isFlagged);
    };

    const handleToggleFlagged = () => {
        const next = !isFlagged;
        setIsFlagged(next);
        fetchMovies(isRead, next);
    };

    const removeFromView = (movieId) => {
        setSections(prev =>
            prev.map(s => ({ ...s, movies: s.movies.filter(m => m.id !== movieId) }))
                .filter(s => s.movies.length > 0)
        );
        setTotalCount(prev => prev - 1);
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/movies/read-all?flagged=${isFlagged}`, { method: "POST" });
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
                    <button className=${`btn btn-sm ${!isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isRead || handleToggleRead()}>Unread</button>
                    <button className=${`btn btn-sm ${isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isRead || handleToggleRead()}>Read</button>
                </div>
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${isFlagged ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isFlagged || handleToggleFlagged()}>Flagged</button>
                    <button className=${`btn btn-sm ${!isFlagged ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isFlagged || handleToggleFlagged()}>Un-Flagged</button>
                </div>
                <div className="tab-count">${totalCount} movies</div>
                ${!isRead && html`
                    <button className="btn btn-secondary btn-sm" onClick=${handleMarkAllRead} disabled=${markingAll}>
                        ${markingAll ? "..." : "Mark All Read"}
                    </button>
                `}
            </div>
            ${loading
                ? html`<div className="loading">Loading movies...</div>`
                : sections.length === 0
                    ? html`<div className="empty-state">
                        <p>${isRead ? "No read movies in this view." : "No movies to display. Run the ingester first:"}</p>
                        ${!isRead && html`<code>python src/cli/main.py</code>`}
                    </div>`
                    : sections.map((section, i) => html`
                        <section key=${i} className="year-section">
                            <h2 className="year-header">${section.label}</h2>
                            <div className="movie-grid">
                                ${section.movies.map(movie => html`
                                    <${MovieCard} key=${movie.id} movie=${movie}
                                        onMarkRead=${!isRead ? removeFromView : undefined}
                                        onMarkUnread=${isRead ? removeFromView : undefined}
                                        onEnrich=${handleEnrich} />
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

function NewsItemRow({ item, isReadView, onRemove }) {
    const [loading, setLoading] = useState(false);

    const handleClick = async () => {
        setLoading(true);
        const action = isReadView ? "unread" : "read";
        try {
            await fetch(`/api/news/items/${item.id}/${action}`, { method: "POST" });
            onRemove(item.id);
        } catch (e) {
            console.error("Failed to toggle read:", e);
        }
        setLoading(false);
    };

    return html`
        <div className="news-item">
            <div className="news-item-header">
                <a className="news-item-title" href=${item.url} target="_blank" rel="noreferrer">${item.title}</a>
                ${item.matched_filter_name && html`<${Badge} className="filter-badge">${item.matched_filter_name}</${Badge}>`}
            </div>
            ${item.published_at && html`<div className="news-item-date">${new Date(item.published_at).toLocaleString()}</div>`}
            <button className="btn btn-read btn-sm" onClick=${handleClick} disabled=${loading}>
                ${loading ? "..." : isReadView ? "Mark Unread" : "Mark Read"}
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// News feed views
// ---------------------------------------------------------------------------

function NewsFeedView({ feedName, emptyMessage, RowComponent }) {
    const [isRead, setIsRead] = useState(false);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const loadItems = (read) => {
        setLoading(true);
        fetch(`/api/news/${encodeURIComponent(feedName)}/items?read=${read}`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    };

    useEffect(() => { loadItems(false); }, [feedName]);

    const handleToggleRead = () => {
        const next = !isRead;
        setIsRead(next);
        loadItems(next);
    };

    const handleRemove = (id) => {
        setItems(prev => prev.filter(item => item.id !== id));
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/news/${encodeURIComponent(feedName)}/read-all`, { method: "POST" });
            setItems([]);
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    return html`
        <div>
            <div className="movies-toolbar">
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${!isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isRead || handleToggleRead()}>Unread</button>
                    <button className=${`btn btn-sm ${isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isRead || handleToggleRead()}>Read</button>
                </div>
                <${FeedToolbar} feedName=${feedName} onMarkAllRead=${handleMarkAllRead} markingAll=${markingAll} showMarkAll=${!isRead} />
            </div>
            ${loading
                ? html`<div className="loading">Loading...</div>`
                : items.length === 0
                    ? html`<div className="empty-state">${isRead ? "No read items." : emptyMessage}</div>`
                    : html`<div className="news-list">
                        ${items.map(item => html`<${RowComponent} key=${item.id} item=${item} isReadView=${isRead} onRemove=${handleRemove} />`)}
                    </div>`
            }
        </div>
    `;
}

function UnfilteredFeedView({ feedName }) {
    return html`<${NewsFeedView} feedName=${feedName} emptyMessage="No items yet." RowComponent=${NewsItemRow} />`;
}

function FilteredFeedView({ feedName }) {
    return html`<${NewsFeedView} feedName=${feedName} emptyMessage="No matched items yet." RowComponent=${NewsItemRow} />`;
}


// ---------------------------------------------------------------------------
// News tab — feed list + active feed view
// ---------------------------------------------------------------------------

function NewsTab({ initialFeedName }) {
    const [feeds, setFeeds] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeFeed, setActiveFeed] = useState(initialFeedName || null);

    useEffect(() => {
        fetch("/api/news")
            .then(r => r.json())
            .then(data => {
                const feedList = data.feeds || [];
                setFeeds(feedList);
                if (feedList.length > 0 && !activeFeed) {
                    const fallback = feedList[0].name;
                    setActiveFeed(fallback);
                    replaceLocation(`/news/${encodeURIComponent(fallback)}`);
                }
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const handleSelectFeed = (feedName) => {
        setActiveFeed(feedName);
        navigate(`/news/${encodeURIComponent(feedName)}`);
    };

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
                        onClick=${() => handleSelectFeed(feed.name)}
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
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Series tab
// ---------------------------------------------------------------------------

function SeriesTab() {
    const [isRead, setIsRead] = useState(false);
    const [isIgnored, setIsIgnored] = useState(false);
    const [seriesList, setSeriesList] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [markingAll, setMarkingAll] = useState(false);
    const [ignoringAll, setIgnoringAll] = useState(false);

    const loadSeries = (read, ignored) => {
        setLoading(true);
        setError(null);
        fetch(`/api/series?read=${read}&ignored=${ignored}`)
            .then(r => r.json())
            .then(data => { setSeriesList(data.series || []); setLoading(false); })
            .catch(() => { setError("Failed to load series"); setLoading(false); });
    };

    useEffect(() => { loadSeries(false, false); }, []);

    const handleToggleRead = () => {
        const next = !isRead;
        setIsRead(next);
        loadSeries(next, isIgnored);
    };

    const handleToggleIgnored = () => {
        const next = !isIgnored;
        setIsIgnored(next);
        loadSeries(isRead, next);
    };

    const removeEpisodeFromView = (episodeId) => {
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

    const handleMarkRead = (episodeId) => {
        fetch(`/api/series/episodes/${episodeId}/read`, { method: "POST" });
        removeEpisodeFromView(episodeId);
    };

    const handleMarkUnread = (episodeId) => {
        fetch(`/api/series/episodes/${episodeId}/unread`, { method: "POST" });
        removeEpisodeFromView(episodeId);
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/series/read-all?ignored=${isIgnored}`, { method: "POST" });
            setSeriesList([]);
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    const handleIgnoreAll = async () => {
        setIgnoringAll(true);
        try {
            await fetch(`/api/series/ignore-all`, { method: "POST" });
            setSeriesList([]);
        } catch (e) {
            console.error("Failed to ignore all series:", e);
        }
        setIgnoringAll(false);
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
                    <button className=${`btn btn-sm ${!isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isRead || handleToggleRead()}>Unread</button>
                    <button className=${`btn btn-sm ${isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isRead || handleToggleRead()}>Read</button>
                </div>
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${!isIgnored ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isIgnored || handleToggleIgnored()}>Not-Ignored</button>
                    <button className=${`btn btn-sm ${isIgnored ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isIgnored || handleToggleIgnored()}>Ignored</button>
                </div>
                <div className="tab-count">${seriesList.length} series</div>
                ${!isRead && html`
                    <button className="btn btn-secondary btn-sm" onClick=${handleMarkAllRead} disabled=${markingAll}>
                        ${markingAll ? "..." : "Mark All Read"}
                    </button>
                `}
                ${!isIgnored && html`
                    <button className="btn btn-secondary btn-sm" onClick=${handleIgnoreAll} disabled=${ignoringAll}>
                        ${ignoringAll ? "..." : "Ignore All"}
                    </button>
                `}
            </div>
            ${seriesList.length === 0
                ? html`<div className="empty-state">
                    ${isIgnored
                        ? "No ignored series."
                        : html`<p>No series to display. Run the ingester first:</p><code>python src/cli/main.py</code>`}
                </div>`
                : seriesList.map(series => html`
                    <div key=${series.id} className="series-block">
                        <h2 className="series-title">
                            <a href=${series.imdb_url} target="_blank" rel="noreferrer">${series.title}</a>
                            ${isIgnored
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
                                            ${!isRead && html`
                                                <button className="btn btn-read btn-sm" onClick=${() => handleMarkRead(ep.id)}>
                                                    Mark Read
                                                </button>
                                            `}
                                            ${isRead && html`
                                                <button className="btn btn-secondary btn-sm" onClick=${() => handleMarkUnread(ep.id)}>
                                                    Mark Unread
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
// Design tab
// ---------------------------------------------------------------------------

function DesignItemCard({ item, isReadView, onRemove }) {
    const [loading, setLoading] = useState(false);

    const handleClick = async () => {
        setLoading(true);
        const action = isReadView ? "unread" : "read";
        try {
            await fetch(`/api/design/items/${item.id}/${action}`, { method: "POST" });
            onRemove(item.id);
        } catch (e) {
            console.error("Failed to toggle read:", e);
        }
        setLoading(false);
    };

    return html`
        <div className="design-card">
            ${item.image_url && html`
                <div className="design-image">
                    <img src=${item.image_url} alt=${item.title} />
                </div>
            `}
            <div className="design-body">
                <h3 className="design-title">
                    <a href=${item.url} target="_blank" rel="noreferrer">${item.title}</a>
                </h3>
                ${item.published_at && html`<div className="design-date">${new Date(item.published_at).toLocaleDateString()}</div>`}
                ${item.summary && html`<p className="design-summary">${item.summary}</p>`}
                <div className="design-actions">
                    <button className="btn btn-read btn-sm" onClick=${handleClick} disabled=${loading}>
                        ${loading ? "..." : isReadView ? "Mark Unread" : "Mark Read"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

function DesignFeedView({ feedName }) {
    const [isRead, setIsRead] = useState(false);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [markingAll, setMarkingAll] = useState(false);

    const loadItems = (read) => {
        setLoading(true);
        fetch(`/api/design/${encodeURIComponent(feedName)}/items?read=${read}`)
            .then(r => r.json())
            .then(data => { setItems(data.items || []); setLoading(false); })
            .catch(() => setLoading(false));
    };

    useEffect(() => { loadItems(false); }, [feedName]);

    const handleToggleRead = () => {
        const next = !isRead;
        setIsRead(next);
        loadItems(next);
    };

    const handleRemove = (id) => {
        setItems(prev => prev.filter(item => item.id !== id));
    };

    const handleMarkAllRead = async () => {
        setMarkingAll(true);
        try {
            await fetch(`/api/design/${encodeURIComponent(feedName)}/read-all`, { method: "POST" });
            setItems([]);
        } catch (e) {
            console.error("Failed to mark all as read:", e);
        }
        setMarkingAll(false);
    };

    return html`
        <div>
            <div className="movies-toolbar">
                <div className="view-toggle">
                    <button className=${`btn btn-sm ${!isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => !isRead || handleToggleRead()}>Unread</button>
                    <button className=${`btn btn-sm ${isRead ? "btn-active" : "btn-secondary"}`}
                        onClick=${() => isRead || handleToggleRead()}>Read</button>
                </div>
                <div className="tab-count">${items.length} items</div>
                ${!isRead && html`
                    <button className="btn btn-secondary btn-sm" onClick=${handleMarkAllRead} disabled=${markingAll}>
                        ${markingAll ? "..." : "Mark All Read"}
                    </button>
                `}
            </div>
            ${loading
                ? html`<div className="loading">Loading...</div>`
                : items.length === 0
                    ? html`<div className="empty-state">${isRead ? "No read items." : "No items yet."}</div>`
                    : html`<div className="design-grid">
                        ${items.map(item => html`<${DesignItemCard} key=${item.id} item=${item} isReadView=${isRead} onRemove=${handleRemove} />`)}
                    </div>`
            }
        </div>
    `;
}

function DesignTab({ initialFeedName }) {
    const [feeds, setFeeds] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeFeed, setActiveFeed] = useState(initialFeedName || null);

    useEffect(() => {
        fetch("/api/design")
            .then(r => r.json())
            .then(data => {
                const feedList = data.feeds || [];
                setFeeds(feedList);
                if (feedList.length > 0 && !activeFeed) {
                    const fallback = feedList[0].name;
                    setActiveFeed(fallback);
                    replaceLocation(`/design/${encodeURIComponent(fallback)}`);
                }
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const handleSelectFeed = (feedName) => {
        setActiveFeed(feedName);
        navigate(`/design/${encodeURIComponent(feedName)}`);
    };

    if (loading) return html`<div className="loading">Loading design feeds...</div>`;
    if (feeds.length === 0) return html`
        <div className="empty-state">
            <p>No design feeds configured. Add <code>design_feeds</code> to your config.yaml.</p>
        </div>
    `;

    return html`
        <div className="news-tab">
            <div className="news-feed-nav">
                ${feeds.map(feed => html`
                    <button
                        key=${feed.name}
                        className=${`feed-nav-btn ${activeFeed === feed.name ? "active" : ""}`}
                        onClick=${() => handleSelectFeed(feed.name)}
                    >
                        ${feed.name}
                        ${feed.unread_count > 0 && html`<span className="unread-badge">${feed.unread_count}</span>`}
                    </button>
                `)}
            </div>
            ${activeFeed && html`
                <div className="news-feed-content">
                    <${DesignFeedView} key=${activeFeed} feedName=${activeFeed} />
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Root app with tab navigation
// ---------------------------------------------------------------------------

function App() {
    const location = useLocation();
    const { tab: activeTab, feedName } = location;

    const handleTabClick = (tab) => navigate(`/${tab}`);

    return html`
        <div className="app">
            <header className="app-header">
                <h1>pelis-feed</h1>
                <nav className="tab-nav">
                    <button
                        className=${`tab-btn ${activeTab === "movies" ? "active" : ""}`}
                        onClick=${() => handleTabClick("movies")}
                    >
                        Movies
                    </button>
                    <button
                        className=${`tab-btn ${activeTab === "series" ? "active" : ""}`}
                        onClick=${() => handleTabClick("series")}
                    >
                        Series
                    </button>
                    <button
                        className=${`tab-btn ${activeTab === "news" ? "active" : ""}`}
                        onClick=${() => handleTabClick("news")}
                    >
                        News
                    </button>
                    <button
                        className=${`tab-btn ${activeTab === "design" ? "active" : ""}`}
                        onClick=${() => handleTabClick("design")}
                    >
                        Design
                    </button>
                </nav>
            </header>
            <${HealthBanner} />
            <main className="tab-content">
                ${activeTab === "movies" && html`<${MoviesTab} />`}
                ${activeTab === "series" && html`<${SeriesTab} />`}
                ${activeTab === "news" && html`<${NewsTab} key=${feedName} initialFeedName=${feedName} />`}
                ${activeTab === "design" && html`<${DesignTab} key=${feedName} initialFeedName=${feedName} />`}
            </main>
        </div>
    `;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(html`<${App} />`);
