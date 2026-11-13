import { useState } from 'react';
import type { ImageryItem } from '../data/types';
import { dataUrl } from '../data/load';
import { VERDICT } from '../map/colors';
import cx from './cx';
import cameraIcon from '../assets/icons/camera.svg';
import closeIcon from '../assets/icons/close.svg';

export function ImageryPin({ item, active, onClick }: { item: ImageryItem; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={cx('imagery-pin', active && 'is-active')}
      style={{ ['--verdict' as string]: VERDICT[item.verdict].color }}
      aria-label={`Imagery ${item.image_id}: ${VERDICT[item.verdict].label}`}
      aria-expanded={active}
      title={`View image · ${VERDICT[item.verdict].label}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <img src={cameraIcon} width={20} height={20} alt="" draggable={false} />
      <span className="imagery-pin__status" aria-hidden="true" />
    </button>
  );
}

export function ImageryPopup({ item, onClose }: { item: ImageryItem; onClose: () => void }) {
  const [broken, setBroken] = useState(false);
  const [beforeBroken, setBeforeBroken] = useState(false);
  const v = VERDICT[item.verdict];
  const hasBefore = !!item.before_thumb && !beforeBroken;
  return (
    <div className="imagery-popup" onClick={(e) => e.stopPropagation()}>
      <div className="imagery-popup__pair">
        {hasBefore && (
          <div className="imagery-popup__thumb">
            <img src={dataUrl(item.before_thumb!)} alt={`Before Harvey ${item.image_id}`} onError={() => setBeforeBroken(true)} />
            <span className="imagery-popup__label">Before</span>
          </div>
        )}
        <div className="imagery-popup__thumb">
          {!broken && <img src={dataUrl(item.thumb)} alt={`Harvey after-image ${item.image_id}`} onError={() => setBroken(true)} />}
          <span className="imagery-popup__label">{hasBefore ? `After · ${item.date}` : `Harvey after-image · ${item.date}`}</span>
        </div>
      </div>
      <div className="row-between">
        <span className="verdict" style={{ ['--verdict' as string]: v.color }}>
          <i />
          {v.label}
        </span>
        <span className="mono-dim imagery-popup__id" title={item.image_id}>{`${item.image_id.split('_').pop() ?? ''} aerial`}</span>
        <button type="button" className="imagery-popup__close" aria-label="Close" onClick={onClose}>
          <img src={closeIcon} width={14} height={14} alt="" />
        </button>
      </div>
      <p>{item.explanation}</p>
      <span className="hint">Qwen3-VL verdict · GB10 · checks the flood map</span>
    </div>
  );
}
