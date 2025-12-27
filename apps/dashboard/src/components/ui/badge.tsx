import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold font-mono uppercase tracking-wider transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary text-primary-foreground shadow',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground',
        destructive:
          'border-transparent bg-destructive text-destructive-foreground shadow',
        outline: 'text-foreground',
        // Status variants with glowing effects
        active:
          'border-status-active/30 bg-status-active/10 text-status-active glow-green',
        running:
          'border-status-running/30 bg-status-running/10 text-status-running glow-cyan',
        paused:
          'border-status-paused/30 bg-status-paused/10 text-status-paused glow-amber',
        stopped:
          'border-status-stopped/30 bg-status-stopped/10 text-status-stopped',
        error:
          'border-status-error/30 bg-status-error/10 text-status-error glow-red',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
