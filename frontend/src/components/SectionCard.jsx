export function SectionCard({ title, extra, children }) {
  return (
    <section className="section-card">
      {(title || extra) ? (
        <div className="section-head">
          {title ? <h3>{title}</h3> : <span />}
          {extra ? <div>{extra}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}
