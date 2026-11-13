import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DisplayStatus, Fixtures, HouseholdRecord } from './data/types';
import { loadFixtures, loadRecord } from './data/load';
import { api } from './data/api';
import { briefingAt, countStatuses, queueAt, statusAt } from './demo/timeline';
import { useClock } from './demo/useClock';
import { useGpu } from './demo/useGpu';
import { useLiveCall } from './demo/useLiveCall';
import { runDemo, type DirectorContext } from './demo/director';
import SwiftMap, { type MapHandle } from './map/SwiftMap';
import TopBar from './components/TopBar';
import LeftPanel from './components/LeftPanel';
import Gb10Panel from './components/Gb10Panel';
import HouseholdDrawer from './components/HouseholdDrawer';
import { Legend, LiveCallBanner, MapControls, ResultsCard, SheetTag } from './components/Overlays';
import cx from './components/cx';
import './App.css';
import './styles/editorial.css';

const SHOW_GPU_PANEL = false;

export default function App() {
  const [fx, setFx] = useState<Fixtures | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadFixtures().then(setFx, (e: unknown) => setError(String(e)));
  }, []);
  if (error) return <div className="boot boot--error">Could not load fixtures: {error}</div>;
  if (!fx) return <div className="boot">Loading Swift…</div>;
  return <Dashboard fx={fx} />;
}

function Dashboard({ fx }: { fx: Fixtures }) {
  const { meta } = fx;
  const demoId = meta.demo_household_id;
  const clock = useClock(meta.timeline.end_min);
  const mapRef = useRef<MapHandle>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [imageryId, setImageryId] = useState<string | null>(null);
  const [showResults, setShowResults] = useState(false);
  const [scene, setScene] = useState(0);
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const [gpuActive, setGpuActive] = useState(false);
  const { live, start: startLive, reset: resetLive } = useLiveCall(fx.liveFallback);
  const gpu = useGpu(SHOW_GPU_PANEL && gpuActive, fx.gpuSample);

  const households = useMemo(() => new Map(fx.households.map((f) => [f.properties.id, f.properties])), [fx.households]);
  const ids = useMemo(() => [...households.keys()], [households]);
  const addresses = useMemo(() => new Map([...households].map(([id, p]) => [id, p.address])), [households]);

  // Replay statuses at t, with the live call overriding the demo household.
  const statuses = useMemo(() => {
    const s = statusAt(fx.timeline, clock.t);
    if (live.phase === 'running') s.set(demoId, 'calling');
    if (live.phase === 'done') s.set(demoId, live.record?.status ?? (live.callStatus === 'no-answer' ? 'no_answer' : 'unconfirmed'));
    return s;
  }, [fx.timeline, clock.t, live.phase, live.record, live.callStatus, demoId]);

  const counts = useMemo(() => countStatuses(ids, statuses), [ids, statuses]);
  const queue = useMemo(() => queueAt(fx.queue, clock.t), [fx.queue, clock.t]);
  const briefing = useMemo(() => briefingAt(fx.briefings, clock.t), [fx.briefings, clock.t]);

  // Drawer record: live record for the demo house during the call, else the fixture.
  const [record, setRecord] = useState<HouseholdRecord | null>(null);
  const liveSelected = selectedId === demoId && live.phase !== 'idle';
  useEffect(() => {
    if (!selectedId || liveSelected) return;
    let alive = true;
    setRecord(null);
    loadRecord(selectedId).then((r) => alive && setRecord(r));
    return () => {
      alive = false;
    };
  }, [selectedId, liveSelected]);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (live.phase !== 'running') return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live.phase]);
  const liveElapsed = live.startedAt ? Math.max(0, (now - live.startedAt) / 1000) : 0;

  const select = useCallback((id: string) => {
    setSelectedId(id);
    setImageryId(null);
  }, []);
  const pick = useCallback((id: string) => {
    select(id);
    mapRef.current?.flyTo(id);
  }, [select]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedId(null);
        setImageryId(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // ---- Run Demo director ----
  const abortRef = useRef<AbortController | null>(null);
  const tRef = useRef(clock.t);
  tRef.current = clock.t;

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    resetLive();
    clock.pause();
    setRunning(false);
    setScene(0);
    setGpuActive(false);
  }, [clock, resetLive]);

  const run = useCallback(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    resetLive();
    setFinished(false);
    setRunning(true);
    const ctx: DirectorContext = {
      setScene,
      flyIn: () => mapRef.current?.flyIn(),
      resetView: () => mapRef.current?.resetNorth(),
      seek: clock.seek,
      play: (speed) => {
        clock.setSpeed(speed);
        clock.play();
      },
      pause: clock.pause,
      startGpu: () => {
        setGpuActive(true);
        api.simulateLive().catch(() => undefined);
      },
      openTopRanked: () => {
        const top = queueAt(fx.queue, tRef.current)[0]?.household_id ?? fx.timeline.find((e) => e.status === 'needs_help' && e.t_min <= tRef.current)?.household_id;
        if (top) pick(top);
      },
      openImagery: () => {
        const first = fx.imagery[0];
        if (first) {
          setSelectedId(null);
          setImageryId(first.image_id);
        }
      },
      closeOverlays: () => {
        setSelectedId(null);
        setImageryId(null);
        setShowResults(false);
      },
      startLiveCall: () => {
        pick(demoId);
        return startLive();
      },
      showResults: () => {
        setSelectedId(null);
        setImageryId(null);
        setShowResults(true);
      },
    };
    runDemo(ctx, ctrl.signal).then(
      () => {
        setRunning(false);
        setFinished(true);
      },
      () => undefined,
    );
  }, [clock, fx, demoId, pick, resetLive, startLive]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const drawerOpen = !!selectedId && households.has(selectedId);
  const liveMode = live.phase !== 'idle';
  const mode = liveMode && !showResults ? 'live' : !running && clock.t === 0 && !finished ? 'ready' : 'replay';
  const selectedStatus: DisplayStatus = selectedId ? statuses.get(selectedId) ?? 'not_called' : 'not_called';
  const rank = selectedId ? queue.findIndex((q) => q.household_id === selectedId) + 1 || null : null;

  return (
    <div className={cx('app', drawerOpen && 'has-drawer', showResults && 'has-results')}>
      <div className="map-layer">
        <SwiftMap
          ref={mapRef}
          fx={fx}
          t={clock.t}
          statuses={statuses}
          selectedId={liveMode && selectedId === demoId ? null : selectedId}
          liveId={live.phase === 'running' ? demoId : null}
          imageryId={imageryId}
          onSelect={select}
          onImagery={(id) => {
            setImageryId(id);
            if (id) setSelectedId(null);
          }}
        />
      </div>

      <TopBar
        clock={clock}
        startIso={meta.timeline.start_iso}
        households={ids.length}
        mode={mode}
        scene={scene}
        running={running}
        finished={finished}
        onRun={run}
        onStop={stop}
      />

      <LeftPanel counts={counts} queue={queue} addresses={addresses} statuses={statuses} briefing={briefing} selectedId={selectedId} onPick={pick} />
      {SHOW_GPU_PANEL && <Gb10Panel gpu={gpu} shifted={drawerOpen} />}
      {liveMode && !showResults && <LiveCallBanner live={live} elapsedS={liveElapsed} />}

      <div className="bottom-chrome">
        <Legend narrow={drawerOpen || showResults} />
        {!showResults && <SheetTag scene={scene} live={liveMode} />}
      </div>
      <span className="attribution">© CARTO © OpenStreetMap</span>
      <MapControls onZoomIn={() => mapRef.current?.zoomBy(0.75)} onZoomOut={() => mapRef.current?.zoomBy(-0.75)} onNorth={() => mapRef.current?.resetNorth()} />

      {drawerOpen && selectedId && (
        <HouseholdDrawer
          household={households.get(selectedId)!}
          status={selectedStatus}
          record={liveSelected ? live.record : record}
          transcript={liveSelected ? live.transcript : record?.transcript ?? []}
          rank={rank}
          live={liveSelected ? { callStatus: live.callStatus, source: live.source, elapsedS: liveElapsed } : null}
          onClose={() => setSelectedId(null)}
          onFly={() => mapRef.current?.flyTo(selectedId)}
        />
      )}

      {showResults && <ResultsCard r={fx.results} onClose={() => setShowResults(false)} />}
    </div>
  );
}
