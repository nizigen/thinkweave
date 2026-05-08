export function ContentCard({ title, subtitle, tags = [], status, onClick }) {
  return (
    <button type="button" className="content-card" onClick={onClick}>
      <div className="cover-placeholder" aria-hidden="true" />
      <div className="content-main">
        <div className="card-title-row">
          <strong>{title}</strong>
          {status ? <span className="status-pill">{status}</span> : null}
        </div>
        {subtitle ? <p>{subtitle}</p> : null}
        {tags.length ? (
          <div className="tag-row">
            {tags.map((tag) => (
              <span key={tag} className="soft-tag">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </button>
  )
}
