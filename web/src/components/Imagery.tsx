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
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <img src={cameraIcon} width={14} height={14} alt="" />
    </button>
  );
}

export function ImageryPopup({ item, onClose }: { item: ImageryItem; onClose: () => void }) {
  const [broken, setBroken] = useState(false);
  const v = VERDICT[item.verdict];
  return (
    <div className="imagery-popup" onClick={(e) => e.stopPropagation()}>
      <div className="imagery-popup__thumb">
        {!broken && <img src={dataUrl(item.thumb)} alt={`Harvey after-image ${item.image_id}`} onError={() => setBroken(true)} />}
        <span>Harvey after-image</span>
      </div>
      <div className="row-between">
        <span className="verdict" style={{ ['--verdict' as string]: v.color }}>
          <i />
          {v.label}
        </span>
        <span className="mono-dim">{item.image_id}</span>
        <button type="button" className="imagery-popup__close" aria-label="Close" onClick={onClose}>
          <img src={closeIcon} width={14} height={14} alt="" />
        </button>
      </div>
      <p>{item.explanation}</p>
      <span className="hint">Qwen3-VL verdict · GB10 · checks the flood map</span>
    </div>
  );
}
