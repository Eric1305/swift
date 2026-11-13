import type { CSSProperties } from 'react';
import { SPEEDS, type Clock } from '../demo/useClock';
import { SCENE_COUNT } from '../demo/director';
import { formatClock, formatT } from '../demo/timeline';
import { Button, IconButton } from './ui';
import cx from './cx';
import swiftLogo from '../assets/swift-logo.png';
import navbarPlayIcon from '../assets/icons/navbar-play.svg';
import playIcon from '../assets/icons/play.svg';
import pauseIcon from '../assets/icons/pause.svg';
import './TopBar.css';

interface Props {
  clock: Clock;
  startIso: string;
  timeScale?: number;
  households: number;
  mode: 'ready' | 'replay' | 'live';
  scene: number;
  running: boolean;
  finished: boolean;
  onRun: () => void;
  onStop: () => void;
  /** Split layout: the clock controls live in the bottom playback bar; the top bar shows place + elapsed time. */
  split?: boolean;
}

export default function TopBar({ clock, startIso, timeScale, households, mode, scene, running, finished, onRun, onStop, split }: Props) {
  const progress = clock.endMin ? clock.t / clock.endMin : 0;
  return (
    <header className="top-bar top-bar--compact">
      <div className="top-bar__brand" aria-label={`Swift · Bear Creek, Houston · Harvey replay · ${households} households`}>
        <span className="top-bar__mascot" aria-hidden="true">
          <img className="top-bar__logo" src={swiftLogo} width={62} height={62} alt="" />
        </span>
        <div className="brand-text">
          <strong>Swift</strong>
        </div>
        {mode === 'live' && <span className="mode-pill mode-pill--live" role="status">
          <i />
          LIVE CALL
        </span>}
      </div>

      {split ? (
        <div className="top-bar__place">
          <span>Bear Creek, Houston</span>
          <em>Hurricane Harvey replay · {households} homes</em>
        </div>
      ) : (
      <div className="top-bar__clock">
        <IconButton icon={clock.playing ? pauseIcon : playIcon} label={clock.playing ? 'Pause' : 'Play'} onClick={clock.toggle} />
        <div className="clock">
          <strong>{formatT(clock.t)}</strong>
          <span>{formatClock(startIso, clock.t, timeScale)}</span>
        </div>
        <input
          className="scrubber"
          type="range"
          min={0}
          max={clock.endMin}
          step={0.5}
          value={clock.t}
          onChange={(e) => clock.seek(Number(e.target.value))}
          aria-label="Replay time"
          style={{ '--progress': `${progress * 100}%` } as CSSProperties}
        />
        <div className="speed" role="radiogroup" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={clock.speed === s}
              className={cx('speed__opt', clock.speed === s && 'is-active')}
              onClick={() => clock.setSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>
      )}

      <div className="top-bar__demo">
        {split && (
          <div className="top-bar__since">
            <span>Since the warning</span>
            <strong>{formatT(clock.t).replace('T+', '')}</strong>
            <em>{formatClock(startIso, clock.t, timeScale)}</em>
          </div>
        )}
        {running ? (
          <>
            <div className="stepper" aria-label={`Scene ${scene} of ${SCENE_COUNT}`}>
              <span>
                Scene {scene}/{SCENE_COUNT}
              </span>
              <div className="stepper__bars">
                {Array.from({ length: SCENE_COUNT }, (_, k) => (
                  <i key={k} className={cx(k + 1 < scene && 'is-done', k + 1 === scene && 'is-current')} />
                ))}
              </div>
            </div>
            <Button variant="ghost" onClick={onStop}>
              Stop
            </Button>
          </>
        ) : (
          <Button variant="primary" className="top-bar__run" onClick={onRun}>
            <img src={navbarPlayIcon} width={12} height={12} alt="" />
            {finished ? 'Replay demo' : 'Run Demo'}
          </Button>
        )}
      </div>
    </header>
  );
}
