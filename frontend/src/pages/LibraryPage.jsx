import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { CategoryTabs } from '../components/CategoryTabs'
import { ContentCard } from '../components/ContentCard'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'

const categories = [
  { label: 'Anime', value: 'anime' },
  { label: 'Comic', value: 'comic' },
  { label: 'Novel', value: 'novel' },
  { label: 'Game', value: 'game' },
  { label: 'Goods', value: 'goods' },
]

const demoCollection = [
  { id: 'a1', title: '风之轨迹', subtitle: '第 9 话 · 追番中', status: 'Watching', tags: ['Anime', 'Fantasy'] },
  { id: 'c1', title: '星河回响', subtitle: 'Vol.4 · 连载中', status: 'Reading', tags: ['Comic', 'Sci-Fi'] },
  { id: 'n1', title: '夜色旅人', subtitle: 'Chapter 32 · 进行中', status: 'Reading', tags: ['Novel', 'Adventure'] },
  { id: 'g1', title: 'Dawn Script', subtitle: '主线 58% · 本周继续', status: 'Playing', tags: ['Game', 'RPG'] },
  { id: 'm1', title: '限定手办系列', subtitle: '收藏 6 件', status: 'Collecting', tags: ['Goods', 'Figure'] },
]

export function LibraryPage() {
  const navigate = useNavigate()
  const [category, setCategory] = useState('anime')
  const [keyword, setKeyword] = useState('')

  const items = useMemo(() => {
    const lower = keyword.trim().toLowerCase()
    return demoCollection.filter((item) => {
      const inCategory = item.tags[0].toLowerCase() === category
      const match = !lower || item.title.toLowerCase().includes(lower)
      return inCategory && match
    })
  }, [category, keyword])

  return (
    <div className="page-stack">
      <PageHeader title="内容库" subtitle="统一管理动画、漫画、小说、游戏与周边收藏。" />
      <SectionCard>
        <div className="toolbar-row">
          <CategoryTabs items={categories} value={category} onChange={setCategory} />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索标题"
            aria-label="搜索标题"
          />
        </div>
      </SectionCard>

      {items.length ? (
        <div className="card-grid">
          {items.map((item) => (
            <ContentCard
              key={item.id}
              title={item.title}
              subtitle={item.subtitle}
              status={item.status}
              tags={item.tags}
              onClick={() => navigate('/history')}
            />
          ))}
        </div>
      ) : (
        <SectionCard>
          <EmptyState title="该分类暂无内容" description="切换分类或调整搜索条件。" />
        </SectionCard>
      )}
    </div>
  )
}
