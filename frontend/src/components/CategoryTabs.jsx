export function CategoryTabs({ items, value, onChange }) {
  return (
    <div className="category-tabs" role="tablist" aria-label="内容分类">
      {items.map((item) => {
        const active = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={`chip-btn${active ? ' is-active' : ''}`}
            onClick={() => onChange(item.value)}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
