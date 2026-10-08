// @ts-nocheck
/** @param {{ variant?: 'primary'|'secondary'|'tertiary'|'danger', size?: 'sm'|'md', loading?: boolean, loadingLabel?: string, icon?: import('react').ReactNode, children?: import('react').ReactNode, className?: string, type?: 'button'|'submit', disabled?: boolean, onClick?: () => void, title?: string }} props */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  loadingLabel = 'Saving…',
  icon = null,
  children,
  className = '',
  type = 'button',
  disabled = false,
  ...rest
}) {
  const tones = {
    primary: 'bg-[#0F766E] text-white hover:bg-[#115E59]',
    secondary: 'bg-white border border-[#CBD5E1] text-[#0F172A] hover:bg-slate-50',
    tertiary: 'bg-transparent text-[#0F766E] hover:underline',
    danger: 'bg-[#B91C1C] text-white hover:bg-red-800',
  };
  const height = size === 'sm' ? 'h-8 px-3' : 'h-9 px-3.5';
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F766E] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${height} ${tones[variant]} ${className}`}
      {...rest}
    >
      {icon}
      {loading ? loadingLabel : children}
    </button>
  );
}
