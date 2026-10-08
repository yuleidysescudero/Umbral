/**
 * Logo de TVN. NO se dibuja ni se recrea: solo se usan los archivos oficiales que el equipo coloca en
 * public/brand/tvn/ (tvn-logo-white.png …) y se activan con PUBLIC_TVN_LOGO=1. Mientras no existan, se muestra un
 * marcador de texto «TVN» en un círculo blanco (TODO visible en el README).
 */
const OFFICIAL = String(import.meta.env.PUBLIC_TVN_LOGO ?? '').trim() === '1';

export function TvnLogo({ size = 36, variant = 'white' }: { size?: number; variant?: 'white' | 'color' }) {
  if (OFFICIAL) {
    return (
      <img
        src={variant === 'white' ? '/brand/tvn/tvn-logo-white.png' : '/brand/tvn/tvn-logo.png'}
        alt="TVN"
        width={size}
        height={size}
        className="shrink-0"
        style={{ width: size, height: size, objectFit: 'contain' }}
      />
    );
  }
  return (
    <span className="tvn-logo" role="img" aria-label="TVN" style={{ width: size, height: size, fontSize: size * 0.34 }} data-testid="tvn-logo-placeholder">
      TVN
    </span>
  );
}
