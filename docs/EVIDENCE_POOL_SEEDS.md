# Evidence Pool Seeds

本文档用于沉淀研究阶段优先使用的证据入口站点，供 `researcher/writer/reviewer/consistency` 节点共用。

## Patent Seeds

- https://patentscope.wipo.int/
- https://worldwide.espacenet.com/
- https://patents.google.com/
- https://www.uspto.gov/patents
- https://www.cnipa.gov.cn/
- https://depatisnet.dpma.de/

## OA Seeds

- https://doaj.org/
- https://pmc.ncbi.nlm.nih.gov/
- https://europepmc.org/
- https://openalex.org/
- https://arxiv.org/
- https://zenodo.org/
- https://hal.science/
- https://plos.org/

## Industry Report Seeds

- https://www.worldbank.org/en/publication
- https://www.imf.org/en/Publications
- https://www.oecd-ilibrary.org/
- https://www.weforum.org/reports/
- https://www.mckinsey.com/featured-insights
- https://www2.deloitte.com/global/en/insights.html
- https://www.pwc.com/gx/en/insights.html
- https://www.gartner.com/en/research

## Fiction / Longform Narrative Seeds

- https://www.gutenberg.org/
- https://standardebooks.org/
- https://librivox.org/
- https://zh.wikisource.org/
- https://ctext.org/
- https://www.poetryfoundation.org/

## Integration Notes

- 研究节点输出 `evidence_ledger` 后，调度器会自动生成任务级 evidence pool：
  - 路径：`backend/artifacts/evidence_pool/task_<task_id>.md`
  - 同步写入 `task.checkpoint_data["evidence_pool"]`
- 种子按 mode 自动分发：
  - `report`: OA + Patent + Industry Report
  - `novel`: Fiction Reference (+ OA)
  - 其他: OA + Patent
- 写作/审查/一致性节点会收到：
  - `evidence_pool_summary`
  - `evidence_pool_markdown`
- 研究节点额外收到：
  - `evidence_pool_seeds`
