import { useMemo, useState } from 'react'
import type { DragEvent, ReactNode } from 'react'

type TicketStatus = 'todo' | 'inProgress' | 'done'
type Priority = 'highest' | 'high' | 'medium' | 'low'

type Ticket = {
  id: string
  title: string
  description: string
  status: TicketStatus
  label: string
  priority: Priority
  assignee: {
    name: string
    initials: string
    color: string
  }
  comments?: number
  dueDate?: string
}

type IconName =
  | 'backlog'
  | 'bell'
  | 'board'
  | 'calendar'
  | 'check'
  | 'chevronDown'
  | 'comment'
  | 'filter'
  | 'help'
  | 'more'
  | 'plus'
  | 'report'
  | 'roadmap'
  | 'search'
  | 'settings'
  | 'share'
  | 'sparkles'

const columns: Array<{
  id: TicketStatus
  title: string
  className: string
}> = [
  { id: 'todo', title: '미실행 프롬프트', className: 'todo' },
  { id: 'inProgress', title: '진행중', className: 'in-progress' },
  { id: 'done', title: '완료', className: 'done' },
]

const initialTickets: Ticket[] = [
  {
    id: 'PRM-142',
    title: '고객 VOC를 주간 리포트로 요약',
    description: '상담 채널의 핵심 이슈와 감정 변화를 한눈에 정리합니다.',
    status: 'todo',
    label: 'VOC',
    priority: 'highest',
    assignee: { name: '박지훈', initials: 'PJ', color: '#6554c0' },
    comments: 4,
    dueDate: '8월 26일',
  },
  {
    id: 'PRM-138',
    title: '신규 가입자 온보딩 메일 초안',
    description: '고객 세그먼트별 환영 메일 카피를 생성합니다.',
    status: 'todo',
    label: 'Marketing',
    priority: 'medium',
    assignee: { name: '서유진', initials: 'SY', color: '#00875a' },
    comments: 2,
  },
  {
    id: 'PRM-136',
    title: '경쟁사 업데이트 모니터링',
    description: '주요 경쟁사의 제품·가격 변경 사항을 수집합니다.',
    status: 'todo',
    label: 'Research',
    priority: 'low',
    assignee: { name: '한도윤', initials: 'HD', color: '#0065ff' },
    dueDate: '8월 28일',
  },
  {
    id: 'PRM-131',
    title: 'FAQ 문서에서 답변 근거 찾기',
    description: '문의 내용과 관련된 정책 문단을 찾아 함께 제공합니다.',
    status: 'todo',
    label: 'Support',
    priority: 'high',
    assignee: { name: '박지훈', initials: 'PJ', color: '#6554c0' },
  },
  {
    id: 'PRM-129',
    title: '8월 캠페인 성과 리포트 작성',
    description: '채널별 전환율과 핵심 인사이트를 요약하고 있습니다.',
    status: 'inProgress',
    label: 'Marketing',
    priority: 'highest',
    assignee: { name: '김민경', initials: 'MK', color: '#de350b' },
    comments: 7,
    dueDate: '오늘',
  },
  {
    id: 'PRM-125',
    title: '고객 문의 답변 초안 생성',
    description: '반품 및 교환 문의에 사용할 답변을 검토 중입니다.',
    status: 'inProgress',
    label: 'Support',
    priority: 'medium',
    assignee: { name: '박지훈', initials: 'PJ', color: '#6554c0' },
    comments: 3,
  },
  {
    id: 'PRM-118',
    title: '결제 이탈 징후 고객 분류',
    description: '최근 행동 데이터를 기준으로 위험 고객을 분류합니다.',
    status: 'inProgress',
    label: 'Data',
    priority: 'high',
    assignee: { name: '이준호', initials: 'JH', color: '#00a3bf' },
    dueDate: '8월 25일',
  },
  {
    id: 'PRM-114',
    title: 'v2.4 제품 릴리즈 노트 작성',
    description: '배포된 기능과 개선 사항을 고객 언어로 정리했습니다.',
    status: 'done',
    label: 'Product',
    priority: 'medium',
    assignee: { name: '정다은', initials: 'DE', color: '#ff8b00' },
    comments: 5,
  },
  {
    id: 'PRM-109',
    title: '주간 회의 액션 아이템 정리',
    description: '담당자와 기한을 포함한 후속 작업 목록을 생성했습니다.',
    status: 'done',
    label: 'Operations',
    priority: 'low',
    assignee: { name: '박지훈', initials: 'PJ', color: '#6554c0' },
    comments: 1,
  },
]

const priorityLabels: Record<Priority, string> = {
  highest: '최우선',
  high: '높음',
  medium: '보통',
  low: '낮음',
}

const iconPaths: Record<IconName, ReactNode> = {
  backlog: <path d="M4 6h16M4 12h16M4 18h11" />,
  bell: <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />,
  board: <path d="M4 4h6v16H4zM14 4h6v10h-6z" />,
  calendar: <path d="M5 3v3m14-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" />,
  check: <path d="m6 12 4 4 8-8" />,
  chevronDown: <path d="m7 9 5 5 5-5" />,
  comment: <path d="M20 15a2 2 0 0 1-2 2H9l-5 4V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2Z" />,
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  help: <path d="M9.5 9a2.6 2.6 0 1 1 4.3 2c-1.3.9-1.8 1.4-1.8 3m0 4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z" />,
  more: <path d="M5 12h.01M12 12h.01M19 12h.01" />,
  plus: <path d="M12 5v14M5 12h14" />,
  report: <path d="M5 20V10m7 10V4m7 16v-7" />,
  roadmap: <path d="M6 3v18M18 3v18M6 7h7l-2 3 2 3H6M18 11h-4l2 3-2 3h4" />,
  search: <path d="m21 21-4.4-4.4M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" />,
  settings: <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />,
  share: <path d="M8 12v7a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1h-7m3-4H4v11m0-11 4 4M4 4l4-4" />,
  sparkles: <path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Zm6 10 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13ZM6 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3Z" />,
}

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {iconPaths[name]}
    </svg>
  )
}

function PriorityMark({ priority }: { priority: Priority }) {
  const mark = {
    highest: '↑↑',
    high: '↑',
    medium: '＝',
    low: '↓',
  }[priority]

  return (
    <span
      className={`priority priority-${priority}`}
      title={`우선순위: ${priorityLabels[priority]}`}
      aria-label={`우선순위 ${priorityLabels[priority]}`}
    >
      {mark}
    </span>
  )
}

function App() {
  const [tickets, setTickets] = useState(initialTickets)
  const [draggedTicketId, setDraggedTicketId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<TicketStatus | null>(null)
  const [query, setQuery] = useState('')
  const [mineOnly, setMineOnly] = useState(false)
  const [highPriorityOnly, setHighPriorityOnly] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  const visibleTickets = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko')

    return tickets.filter((ticket) => {
      const matchesQuery =
        !normalizedQuery ||
        `${ticket.id} ${ticket.title} ${ticket.description} ${ticket.label}`
          .toLocaleLowerCase('ko')
          .includes(normalizedQuery)
      const matchesAssignee = !mineOnly || ticket.assignee.initials === 'PJ'
      const matchesPriority =
        !highPriorityOnly ||
        ticket.priority === 'highest' ||
        ticket.priority === 'high'

      return matchesQuery && matchesAssignee && matchesPriority
    })
  }, [highPriorityOnly, mineOnly, query, tickets])

  const completedCount = tickets.filter((ticket) => ticket.status === 'done').length
  const completionRate = Math.round((completedCount / tickets.length) * 100)

  const handleDragStart = (
    event: DragEvent<HTMLElement>,
    ticketId: string,
  ) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', ticketId)
    setDraggedTicketId(ticketId)
  }

  const handleDrop = (
    event: DragEvent<HTMLElement>,
    nextStatus: TicketStatus,
  ) => {
    event.preventDefault()
    const ticketId =
      event.dataTransfer.getData('text/plain') || draggedTicketId
    const ticket = tickets.find((item) => item.id === ticketId)

    if (!ticket) {
      setDraggedTicketId(null)
      setDropTarget(null)
      return
    }

    if (ticket.status !== nextStatus) {
      setTickets((current) => {
        const movedTicket = current.find((item) => item.id === ticketId)
        if (!movedTicket) return current

        return [
          ...current.filter((item) => item.id !== ticketId),
          { ...movedTicket, status: nextStatus },
        ]
      })

      const columnTitle = columns.find((column) => column.id === nextStatus)?.title
      setAnnouncement(`${ticket.id} 티켓을 ${columnTitle} 열로 이동했습니다.`)
    }

    setDraggedTicketId(null)
    setDropTarget(null)
  }

  const handleDragLeave = (
    event: DragEvent<HTMLElement>,
    status: TicketStatus,
  ) => {
    const nextElement = event.relatedTarget as Node | null
    if (!nextElement || !event.currentTarget.contains(nextElement)) {
      setDropTarget((current) => (current === status ? null : current))
    }
  }

  return (
    <div className="app">
      <header className="top-nav">
        <a className="product-logo" href="#board" aria-label="Prompt Jira 홈">
          <span className="product-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <strong>Jira</strong>
        </a>

        <nav className="global-nav" aria-label="전역 메뉴">
          <button type="button">
            최근 항목 <Icon name="chevronDown" size={14} />
          </button>
          <button type="button">
            프로젝트 <Icon name="chevronDown" size={14} />
          </button>
          <button type="button">
            필터 <Icon name="chevronDown" size={14} />
          </button>
          <button type="button">대시보드</button>
          <button type="button">팀</button>
        </nav>

        <button className="create-button" type="button">만들기</button>

        <div className="top-nav-spacer" />

        <label className="global-search">
          <Icon name="search" size={17} />
          <input type="search" placeholder="검색" aria-label="전체 검색" />
        </label>
        <button className="icon-button" type="button" aria-label="알림">
          <Icon name="bell" />
          <span className="notification-dot" />
        </button>
        <button className="icon-button" type="button" aria-label="도움말">
          <Icon name="help" />
        </button>
        <button className="icon-button" type="button" aria-label="설정">
          <Icon name="settings" />
        </button>
        <span className="avatar top-avatar" title="박지훈">PJ</span>
      </header>

      <div className="workspace-shell">
        <aside className="sidebar">
          <div className="project-summary">
            <span className="project-icon">
              <Icon name="sparkles" size={22} />
            </span>
            <div>
              <strong>Prompt Studio</strong>
              <span>소프트웨어 프로젝트</span>
            </div>
          </div>

          <nav className="project-nav" aria-label="프로젝트 메뉴">
            <a href="#board">
              <Icon name="roadmap" />
              로드맵
            </a>
            <a href="#board">
              <Icon name="backlog" />
              백로그
            </a>
            <a className="active" href="#board" aria-current="page">
              <Icon name="board" />
              보드
            </a>
            <a href="#board">
              <Icon name="report" />
              보고서
            </a>
          </nav>

          <div className="sidebar-divider" />

          <nav className="project-nav secondary" aria-label="프로젝트 설정">
            <a href="#board">
              <Icon name="calendar" />
              캘린더
            </a>
            <a href="#board">
              <Icon name="settings" />
              프로젝트 설정
            </a>
          </nav>

          <div className="sidebar-tip">
            <span><Icon name="sparkles" size={16} /></span>
            <p>
              <strong>프롬프트 자동화</strong>
              티켓을 이동해 실행 상태를 관리하세요.
            </p>
          </div>
        </aside>

        <main className="board-page" id="board">
          <div className="breadcrumbs">
            프로젝트 <span>/</span> Prompt Studio <span>/</span> 보드
          </div>

          <section className="board-heading">
            <div>
              <span className="board-kicker">PROMPT OPERATIONS</span>
              <h1>프롬프트 실행 보드</h1>
              <p>운영 프롬프트의 실행 상태를 한 곳에서 관리합니다.</p>
            </div>
            <div className="heading-actions">
              <button type="button" className="secondary-button">
                <Icon name="share" size={16} />
                공유
              </button>
              <button type="button" className="more-button" aria-label="더 보기">
                <Icon name="more" />
              </button>
            </div>
          </section>

          <section className="board-toolbar" aria-label="보드 필터">
            <label className="ticket-search">
              <Icon name="search" size={17} />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="이 보드 검색"
                aria-label="티켓 검색"
              />
            </label>

            <div className="member-stack" aria-label="프로젝트 멤버">
              {[
                ['PJ', '#6554c0'],
                ['SY', '#00875a'],
                ['MK', '#de350b'],
                ['+3', '#44546f'],
              ].map(([initials, color]) => (
                <span
                  className="avatar"
                  style={{ backgroundColor: color }}
                  key={initials}
                >
                  {initials}
                </span>
              ))}
            </div>

            <button
              type="button"
              className={`filter-button ${mineOnly ? 'active' : ''}`}
              aria-pressed={mineOnly}
              onClick={() => setMineOnly((current) => !current)}
            >
              내 티켓만
            </button>
            <button
              type="button"
              className={`filter-button ${highPriorityOnly ? 'active' : ''}`}
              aria-pressed={highPriorityOnly}
              onClick={() => setHighPriorityOnly((current) => !current)}
            >
              <Icon name="filter" size={15} />
              높은 우선순위
            </button>

            <div className="toolbar-spacer" />

            <div className="progress-summary">
              <span>{completedCount}/{tickets.length} 완료</span>
              <div className="progress-track" aria-label={`완료율 ${completionRate}%`}>
                <span style={{ width: `${completionRate}%` }} />
              </div>
            </div>
          </section>

          <div className="board-caption">
            <span className="live-dot" />
            활성 프롬프트
            <span className="caption-divider" />
            카드를 드래그해서 상태를 변경하세요
          </div>

          <section className="board-grid" aria-label="프롬프트 칸반 보드">
            {columns.map((column) => {
              const columnTickets = visibleTickets.filter(
                (ticket) => ticket.status === column.id,
              )

              return (
                <section
                  className={`board-column ${column.className} ${
                    dropTarget === column.id ? 'is-over' : ''
                  }`}
                  key={column.id}
                  onDragEnter={(event) => {
                    event.preventDefault()
                    setDropTarget(column.id)
                  }}
                  onDragOver={(event) => {
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                  }}
                  onDragLeave={(event) => handleDragLeave(event, column.id)}
                  onDrop={(event) => handleDrop(event, column.id)}
                >
                  <header className="column-header">
                    <div>
                      <span className="status-indicator" />
                      <h2>{column.title}</h2>
                      <span className="ticket-count">{columnTickets.length}</span>
                    </div>
                    <button type="button" aria-label={`${column.title} 메뉴`}>
                      <Icon name="more" size={17} />
                    </button>
                  </header>

                  <div className="ticket-list">
                    {columnTickets.map((ticket) => (
                      <article
                        className={`ticket-card ${
                          draggedTicketId === ticket.id ? 'is-dragging' : ''
                        }`}
                        key={ticket.id}
                        draggable
                        onDragStart={(event) => handleDragStart(event, ticket.id)}
                        onDragEnd={() => {
                          setDraggedTicketId(null)
                          setDropTarget(null)
                        }}
                        aria-label={`${ticket.id}: ${ticket.title}`}
                      >
                        <div className="card-topline">
                          <span className="ticket-label">{ticket.label}</span>
                          <button
                            type="button"
                            className="card-menu"
                            aria-label={`${ticket.id} 메뉴`}
                          >
                            <Icon name="more" size={16} />
                          </button>
                        </div>

                        <h3>{ticket.title}</h3>
                        <p>{ticket.description}</p>

                        <div className="card-metadata">
                          {ticket.dueDate && (
                            <span className={`due-date ${ticket.dueDate === '오늘' ? 'urgent' : ''}`}>
                              <Icon name="calendar" size={13} />
                              {ticket.dueDate}
                            </span>
                          )}
                          {ticket.comments !== undefined && (
                            <span className="comments">
                              <Icon name="comment" size={13} />
                              {ticket.comments}
                            </span>
                          )}
                        </div>

                        <footer className="card-footer">
                          <div className="ticket-key">
                            <span className="issue-type">
                              <Icon name="check" size={11} />
                            </span>
                            {ticket.id}
                          </div>
                          <div className="ticket-people">
                            <PriorityMark priority={ticket.priority} />
                            <span
                              className="avatar card-avatar"
                              style={{ backgroundColor: ticket.assignee.color }}
                              title={ticket.assignee.name}
                            >
                              {ticket.assignee.initials}
                            </span>
                          </div>
                        </footer>
                      </article>
                    ))}

                    {columnTickets.length === 0 && (
                      <div className="empty-column">
                        <span><Icon name="plus" size={19} /></span>
                        <strong>
                          {query || mineOnly || highPriorityOnly
                            ? '표시할 티켓이 없습니다'
                            : '티켓을 여기로 이동하세요'}
                        </strong>
                        <p>
                          {query || mineOnly || highPriorityOnly
                            ? '검색어나 필터를 변경해 보세요.'
                            : '다른 열의 카드를 끌어다 놓을 수 있어요.'}
                        </p>
                      </div>
                    )}
                  </div>

                  {draggedTicketId && (
                    <div className="drop-hint">
                      <Icon name="plus" size={16} />
                      여기에 놓기
                    </div>
                  )}
                </section>
              )
            })}
          </section>

          <div className="sr-only" aria-live="polite">
            {announcement}
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
