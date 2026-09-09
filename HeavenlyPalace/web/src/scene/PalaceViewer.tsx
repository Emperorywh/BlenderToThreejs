/* 天宫首页以全屏游览为主，场景、导航和辅助面板各自承担明确职责。
 * 所有按钮均连接真实状态，加载失败、触屏操作及键盘操作有对应反馈。 */
import { useEffect, useRef, useState } from 'react'
import type { PalaceScene } from './createPalaceScene'
import { views } from './views'

/* 图标采用本地矢量线条，与页面的细线装饰保持一致。
 * 图形只作辅助，操作名称由按钮文字和无障碍标签提供。 */
function Icon({ name }: { name: 'play' | 'pause' | 'reset' | 'plus' | 'minus' | 'expand' | 'close' | 'settings' | 'help' | 'eye' | 'arrow' | 'mouse' }) {
  const paths = {
    play: 'm9 5 11 7-11 7Z', pause: 'M8 5v14M16 5v14', reset: 'M4 10a8 8 0 1 1 1 7M4 4v6h6',
    plus: 'M5 12h14M12 5v14', minus: 'M5 12h14', expand: 'M9 4H4v5M15 4h5v5M4 15v5h5M20 15v5h-5',
    close: 'm6 6 12 12M18 6 6 18', settings: 'M4 7h8M16 7h4M4 17h4M12 17h8M12 4v6M8 14v6',
    help: 'M9 9a3 3 0 1 1 5 2.2c-1.2.6-2 1-2 2.8M12 17h.01', eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
    arrow: 'M4 12h15m-6-6 6 6-6 6', mouse: 'M12 3a6 6 0 0 0-6 6v6a6 6 0 0 0 12 0V9a6 6 0 0 0-6-6Zm0 0v6',
  }
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} />{name === 'help' && <circle cx="12" cy="12" r="10" />}</svg>
}

export default function PalaceViewer() {
  const host = useRef<HTMLDivElement>(null), shell = useRef<HTMLElement>(null)
  const api = useRef<PalaceScene | null>(null), dialog = useRef<HTMLDialogElement>(null)
  const previousImmersive = useRef(false)
  const [active, setActive] = useState(0), [free, setFree] = useState(false), [tour, setTour] = useState(false)
  const [ready, setReady] = useState(false), [progress, setProgress] = useState(0), [loading, setLoading] = useState('正在推开云间的门')
  const [error, setError] = useState(''), [attempt, setAttempt] = useState(0)
  const [immersive, setImmersive] = useState(false), [fullscreen, setFullscreen] = useState(false)
  const [panel, setPanel] = useState<'help' | 'settings' | null>(null), [notice, setNotice] = useState('')
  const [motion, setMotion] = useState(() => !matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [quality, setQuality] = useState<'balanced' | 'high'>('balanced')
  const view = views[active], available = ready && !error

  useEffect(() => {
    /* 先显示轻量页面，再异步载入三维引擎，使慢速网络下也能立即获得反馈。
     * 每次挂载独立管理场景实例，重试或退出时不会留下旧的异步初始化。 */
    let cancelled = false, instance: PalaceScene | undefined
    async function mountScene() {
      try {
        const { createPalaceScene } = await import('./createPalaceScene')
        if (cancelled || !host.current) return
        instance = createPalaceScene(host.current, {
          onProgress: (value, message) => { setProgress(previous => Math.max(previous, value)); setLoading(message) },
          onReady: () => setReady(true),
          onError: message => { setError(message); setTour(false); setImmersive(false); setPanel(null) },
          onInteract: () => { setFree(true); setTour(false) },
          onCamera: index => { setActive(index); setFree(false); setTour(false) },
        })
        api.current = instance
      } catch {
        if (!cancelled) setError('浏览器暂时无法显示三维画面，请检查网络与硬件加速设置，或使用支持 WebGL 2 的浏览器重试。')
      }
    }
    void mountScene()
    return () => { cancelled = true; instance?.dispose(); if (api.current === instance) api.current = null }
  }, [attempt])

  /* 画质和动态效果即时应用，不重新下载模型，也不重置当前视角。
   * 系统减少动态效果的偏好在首次进入时生效，访客仍可自行开启。 */
  useEffect(() => { api.current?.setMotion(motion) }, [motion, ready])
  useEffect(() => { api.current?.setQuality(quality) }, [quality, ready])
  useEffect(() => {
    const sync = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 4000)
    return () => clearTimeout(timer)
  }, [notice])
  useEffect(() => {
    if (panel) {
      dialog.current?.showModal()
    } else dialog.current?.close()
  }, [panel])

  /* 面板从用户操作入口统一打开，暂停环游并保留当前镜头位置。
   * 对话框的副作用只负责同步原生打开状态，不额外派生页面状态。 */
  function openPanel(value: 'help' | 'settings') {
    api.current?.setTour(false); setTour(false); setPanel(value)
  }

  function toggleTour() {
    if (!available) return
    api.current?.setTour(!tour)
    setTour(!tour); setFree(true)
  }
  function selectView(index: number) {
    if (!available) return
    api.current?.selectCamera(index)
  }
  function retry() {
    setError(''); setReady(false); setProgress(0); setLoading('正在重新推开云间的门')
    setFree(false); setTour(false); setAttempt(value => value + 1)
  }
  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await shell.current?.requestFullscreen()
    } catch { setNotice('浏览器暂未允许全屏，可使用“沉浸观景”隐藏界面。') }
  }

  /* 快捷键只在画面或页面空白处响应，避免干扰按钮、表单和对话框。
   * 沉浸模式提供可聚焦的返回按钮，退出后将焦点还给原入口。 */
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if (!available || panel || event.altKey || event.ctrlKey || event.metaKey || event.repeat) return
      if (event.key === 'Escape') { setImmersive(false); return }
      if (event.target instanceof Element && event.target.closest('button, input, select, textarea, a, dialog')) return
      const key = event.key.toLowerCase()
      if (/^[1-4]$/.test(key)) selectView(Number(key) - 1)
      else if (key === 'r') selectView(active)
      else if (key === ' ') { event.preventDefault(); toggleTour() }
      else if (key === 'h' || key === '?') openPanel('help')
      else if (key === 'i') setImmersive(value => !value)
    }
    document.addEventListener('keydown', keyboard)
    return () => document.removeEventListener('keydown', keyboard)
  })
  useEffect(() => {
    /* 等待可见性和不可交互状态更新后移动焦点，避免焦点落入隐藏控件。
     * 初次挂载不主动夺取焦点，只有实际切换沉浸模式才执行恢复。 */
    if (previousImmersive.current === immersive) return
    previousImmersive.current = immersive
    document.getElementById(immersive ? 'exit-immersion' : 'enter-immersion')?.focus()
  }, [immersive])

  return <main ref={shell} className={`palace ${ready ? 'is-ready' : ''} ${immersive ? 'is-immersive' : ''}`}>
    <div className="stage" ref={host} aria-busy={!ready} />
    <div className="scene-shade" aria-hidden="true" />
    <div className="scene-interface" inert={immersive || !available}>
      <header className="masthead">
        <a className="brand" href="./" aria-label="天宫首页" onClick={event => { event.preventDefault(); selectView(0) }}>
          <span className="seal">天<br />宫</span><span className="brand-name">天宫<small>HEAVENLY PALACE</small></span>
        </a>
        <div className="header-right"><span className="edition">云上漫游 <span>·</span> 数字仙境</span>
          <button className="text-button immerse-button" id="enter-immersion" disabled={!available} onClick={() => setImmersive(true)}><Icon name="eye" /><span>沉浸观景</span></button>
        </div>
      </header>
      <section className="view-story" key={active} aria-live="polite" aria-atomic="true">
        <p className="eyebrow"><span className="chapter-rule" />天宫四景 <span className="chapter-number">0{active + 1} / 04</span></p>
        <h1>{view.title}</h1><p className="english-title">{view.subtitle}</p>
        <p className="poem">{view.description}</p>
        <button className="story-link" disabled={!available} onClick={() => openPanel('help')}>此间一览 <Icon name="arrow" /></button>
      </section>
      <aside className="scene-tools" aria-label="画面工具">
        <button className="icon-button" aria-label="放大画面" title="放大画面（+）" disabled={!available} onClick={() => api.current?.zoom(1)}><Icon name="plus" /></button>
        <button className="icon-button" aria-label="缩小画面" title="缩小画面（−）" disabled={!available} onClick={() => api.current?.zoom(-1)}><Icon name="minus" /></button>
        <span className="tool-divider" />
        <button className="icon-button" aria-label="恢复当前视角" title="恢复当前视角（R）" disabled={!available} onClick={() => selectView(active)}><Icon name="reset" /></button>
        {document.fullscreenEnabled && <button className="icon-button" aria-label={fullscreen ? '退出全屏' : '全屏显示'} title={fullscreen ? '退出全屏' : '全屏显示'} disabled={!available} onClick={() => void toggleFullscreen()}><Icon name="expand" /></button>}
      </aside>
      <div className="scene-caption" aria-hidden="true"><span>山海有境</span><i /><span>心游无间</span></div>
      <footer className="journey-footer">
        <div className="journey-topline"><span className="journey-label">选一处风景，慢慢看。</span><span className="view-state" role="status"><i className={tour ? 'is-playing' : ''} />{tour ? '正在环游 · 拖动画面即可接管' : free ? '自由观察' : '静赏此景'}</span></div>
        <div className="journey-dock">
          <nav className="view-nav" aria-label="天宫观景视角">{views.map((item, index) => <button key={item.label} className={`view-button ${active === index ? 'selected' : ''}`} aria-pressed={active === index} disabled={!available} onClick={() => selectView(index)}>
            <span className="view-number">0{index + 1}</span><span className="view-name">{item.label}<small>{['环岛 · 观群殿', '中轴 · 赏重檐', '高处 · 寻山水', '月门 · 看流云'][index]}</small></span><span className="view-mark" aria-hidden="true">{item.mark}</span>
          </button>)}</nav>
          <button className={`tour-button ${tour ? 'is-active' : ''}`} aria-pressed={tour} disabled={!available} onClick={toggleTour}><Icon name={tour ? 'pause' : 'play'} /><span>{tour ? '暂停环游' : '自动环游'}</span></button>
        </div>
        <div className="journey-bottomline">
          <p className="interaction-hint" id="scene-instructions"><Icon name="mouse" /><span className="desktop-hint">拖动旋转<span>·</span>滚轮缩放<span>·</span>右键平移</span><span className="touch-hint">单指旋转<span>·</span>双指缩放与平移</span></p>
          <div className="utility-links"><button className="text-button" disabled={!available} onClick={() => openPanel('settings')}><Icon name="settings" />观景设置</button><span /><button className="text-button" disabled={!available} onClick={() => openPanel('help')}><Icon name="help" />游览指南</button></div>
        </div>
      </footer>
    </div>
    {/* 沉浸时保留独立返回控件，隐藏区域同时退出键盘导航和无障碍树。
      * 自动环游的暂停入口仍可用，不要求访客记住快捷键。 */}
    <div className="immersive-controls" inert={!immersive} aria-hidden={!immersive}>
      <button className="text-button" id="exit-immersion" onClick={() => setImmersive(false)}><Icon name="close" />返回界面</button>
      <button className="text-button" onClick={toggleTour} aria-pressed={tour}><Icon name={tour ? 'pause' : 'play'} />{tour ? '暂停环游' : '自动环游'}</button>
    </div>
    <div className={`arrival ${ready && !error ? 'has-arrived' : ''}`} aria-hidden={ready && !error} inert={ready && !error}>
      <span className="arrival-kicker">HEAVENLY PALACE</span>
      <svg className="arrival-roof" viewBox="0 0 280 110" fill="none" stroke="currentColor" strokeWidth="1" aria-hidden="true"><path d="M18 59c49 0 87-20 122-44 35 24 73 44 122 44M35 60h210M53 66h174M77 66v32m126-32v32M96 66v32m88-32v32M67 99h146M62 105h156M109 32h62M135 13l5-7 5 7" /><path d="M5 84h43m184 0h43M20 91h28m184 0h28" opacity=".4" /></svg>
      <h2>{error ? '稍候，再入天宫' : '云深处，天宫见'}</h2>
      {error ? <div className="arrival-error" role="alert"><p>{error}</p><button className="primary-button" onClick={retry}>重新载入 <Icon name="reset" /></button></div> : <>
        <p role="status">{loading}</p><div className="arrival-progress"><progress value={progress} max="100" aria-label="天宫加载进度" /><span>{progress}<small>%</small></span></div>
        <p className="arrival-note">初次相逢需要片刻，静候云开。</p>
      </>}
      <span className="arrival-seal" aria-hidden="true">入境</span>
    </div>
    {/* 原生对话框负责焦点约束和退出后的焦点恢复，窄屏面板可独立滚动。
      * 背景点击与退出键都可以关闭，帮助内容同时覆盖鼠标、触屏和键盘。 */}
    <dialog ref={dialog} className="visitor-dialog" aria-labelledby="panel-title" onCancel={() => setPanel(null)} onClick={event => { if (event.target === event.currentTarget) setPanel(null) }}>
      <div className="dialog-content">
        <div className="dialog-heading"><p className="eyebrow">{panel === 'settings' ? 'MAKE YOURSELF AT HOME' : 'A LITTLE GUIDE'}</p><button className="icon-button" aria-label="关闭面板" autoFocus onClick={() => setPanel(null)}><Icon name="close" /></button></div>
        <h2 id="panel-title">{panel === 'settings' ? '自在观景' : '游于云上'}</h2>
        {panel === 'settings' ? <>
          <p className="dialog-intro">用适合自己的节奏，看一会儿风景。</p>
          <section className="setting-section"><h3>画面细腻度</h3><div className="quality-options" role="group" aria-label="画面细腻度"><button aria-pressed={quality === 'balanced'} onClick={() => setQuality('balanced')}><strong>均衡</strong><span>兼顾清晰与流畅</span></button><button aria-pressed={quality === 'high'} onClick={() => setQuality('high')}><strong>精细</strong><span>呈现更多建筑细节</span></button></div><p className="setting-note">若拖动画面不够流畅，可切回均衡。</p></section>
          <section className="setting-section motion-setting"><div><h3>流云与飞瀑</h3><p>让云雾与水流随时间轻轻变化。</p></div><button className="switch" role="switch" aria-checked={motion} aria-label="流云与飞瀑动态效果" onClick={() => setMotion(value => !value)}><span /></button></section>
          <p className="settings-footnote">设置在本次游览中生效。</p>
        </> : <>
          <p className="dialog-intro">{view.detail}</p>
          <div className="guide-rows"><div><span>01</span><h3>移步换景</h3><p>点击下方四处风景，自由往返全景、正殿、鸟瞰与殿内。</p></div><div><span>02</span><h3>随心细看</h3><p>鼠标拖动旋转，滚轮缩放，右键拖动平移。触屏单指旋转，双指缩放与平移。</p></div><div><span>03</span><h3>让风景流动</h3><p>开启自动环游，慢慢看过宫阙。拖动画面即可接管；点击恢复按钮，回到此景的初始构图。</p></div></div>
          <div className="keyboard-guide"><span>键盘也可以</span><p><kbd>1</kbd>–<kbd>4</kbd> 换景 <kbd>R</kbd> 复位 <kbd>空格</kbd> 环游</p><p><kbd>↑ ↓ ← →</kbd> 转动 <kbd>+ −</kbd> 缩放 <kbd>I</kbd> 沉浸</p></div>
          <button className="primary-button guide-done" onClick={() => setPanel(null)}>继续看风景 <Icon name="arrow" /></button>
        </>}
      </div>
    </dialog>
    {notice && <div className="notice" role="status">{notice}</div>}
  </main>
}
