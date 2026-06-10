import React from 'react'
import { cn } from '@/lib/utils'
import Spinner from './Spinner'

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'destructive'
  | 'ghost'
  | 'outline'

export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  iconLeft?: React.ReactNode
  iconRight?: React.ReactNode
  children?: React.ReactNode
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: [
    'bg-amber-500 hover:bg-amber-400 active:bg-amber-600',
    'text-zinc-950 font-semibold',
    'border-transparent',
    'focus-visible:ring-amber-500/50',
  ].join(' '),
  secondary: [
    'bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-700',
    'text-zinc-200',
    'border-zinc-700 hover:border-zinc-600',
    'focus-visible:ring-zinc-500/50',
  ].join(' '),
  destructive: [
    'bg-red-500/10 hover:bg-red-500/20 active:bg-red-500/30',
    'text-red-400 hover:text-red-300',
    'border-red-500/20 hover:border-red-500/40',
    'focus-visible:ring-red-500/50',
  ].join(' '),
  ghost: [
    'bg-transparent hover:bg-zinc-800',
    'text-zinc-400 hover:text-zinc-200',
    'border-transparent',
    'focus-visible:ring-zinc-500/50',
  ].join(' '),
  outline: [
    'bg-transparent hover:bg-zinc-800',
    'text-zinc-300 hover:text-zinc-100',
    'border-zinc-700 hover:border-zinc-600',
    'focus-visible:ring-zinc-500/50',
  ].join(' '),
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs rounded-md gap-1.5',
  md: 'h-9 px-3.5 text-sm rounded-lg gap-2',
  lg: 'h-11 px-5 text-sm rounded-xl gap-2',
}

export default function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  iconLeft,
  iconRight,
  children,
  disabled,
  className,
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <button
      disabled={isDisabled}
      className={cn(
        'inline-flex items-center justify-center font-medium border',
        'transition-colors duration-150',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <Spinner
          size="sm"
          color={variant === 'primary' ? 'dark' : 'default'}
          className="flex-shrink-0"
        />
      ) : (
        iconLeft && (
          <span className="flex-shrink-0 -ml-0.5">{iconLeft}</span>
        )
      )}
      {children && <span>{children}</span>}
      {!loading && iconRight && (
        <span className="flex-shrink-0 -mr-0.5">{iconRight}</span>
      )}
    </button>
  )
}

export { Button }
