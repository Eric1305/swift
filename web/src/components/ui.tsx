import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { DisplayStatus } from '../data/types';
import { statusVar } from '../map/colors';
import cx from './cx';
import playIcon from '../assets/icons/play-primary.svg';

export const STATUS_LABEL: Record<DisplayStatus, string> = {
  needs_help: 'Needs help',
  can_help: 'Can help',
  safe: 'Safe',
  unconfirmed: 'Unconfirmed',
  no_answer: 'No answer',
  not_called: 'Not called',
  calling: 'Calling…',
};

type Variant = 'primary' | 'secondary' | 'ghost';

export function Button({ variant = 'secondary', children, className, ...rest }: { variant?: Variant; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" className={cx('btn', `btn--${variant}`, className)} {...rest}>
      {variant === 'primary' && <img src={playIcon} width={12} height={12} alt="" className="btn__icon" />}
      {children}
    </button>
  );
}

export function IconButton({ icon, label, ...rest }: { icon: string; label: string } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" className="icon-btn" aria-label={label} title={label} {...rest}>
      <img src={icon} width={14} height={14} alt="" />
    </button>
  );
}

/** Status dot. `not_called` reads as a white roof on the site-plan map. */
export function Dot({ status, size = 8 }: { status: DisplayStatus | 'called'; size?: number }) {
  const s = status === 'called' ? 'calling' : status;
  return <span className={cx('dot', `dot--${s}`)} style={{ width: size, height: size, ['--dot' as string]: statusVar(s) }} />;
}

export function StatusChip({ status }: { status: DisplayStatus }) {
  return (
    <span className={cx('chip', `chip--${status}`)} style={{ ['--chip' as string]: statusVar(status) }}>
      <Dot status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx('eyebrow', className)}>{children}</span>;
}
