export function EmptyState({ title, description, action }) {
  return (
    <div className="empty-state" role="status">
      <p className="empty-title">{title}</p>
      {description ? <p className="empty-desc">{description}</p> : null}
      {action ? <div>{action}</div> : null}
    </div>
  )
}
