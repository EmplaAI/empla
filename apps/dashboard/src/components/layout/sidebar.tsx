import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Plus,
  Activity,
  Plug,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  {
    label: 'Dashboard',
    href: '/',
    icon: LayoutDashboard,
  },
  {
    label: 'Employees',
    href: '/employees',
    icon: Users,
  },
  {
    label: 'Integrations',
    href: '/integrations',
    icon: Plug,
  },
  {
    label: 'Activity',
    href: '/activity',
    icon: Activity,
    disabled: true,
  },
];

const actionItems = [
  {
    label: 'New Employee',
    href: '/employees/new',
    icon: Plus,
  },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation();

  const NavItem = ({
    href,
    icon: Icon,
    label,
    disabled,
  }: {
    href: string;
    icon: typeof LayoutDashboard;
    label: string;
    disabled?: boolean;
  }) => {
    const isActive =
      href === '/' ? location.pathname === '/' : location.pathname.startsWith(href);

    const content = (
      <NavLink
        to={href}
        className={cn(
          'group relative flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200',
          isActive
            ? 'bg-primary/10 text-primary'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
          disabled && 'pointer-events-none opacity-50',
          collapsed && 'justify-center px-2'
        )}
      >
        {/* Active indicator */}
        {isActive && (
          <div className="absolute left-0 top-1/2 h-6 w-0.5 -translate-y-1/2 rounded-full bg-primary shadow-[0_0_8px] shadow-primary" />
        )}
        <Icon className={cn('h-5 w-5 shrink-0', isActive && 'text-primary')} />
        {!collapsed && <span>{label}</span>}
      </NavLink>
    );

    if (collapsed) {
      return (
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>{content}</TooltipTrigger>
          <TooltipContent side="right" className="font-medium">
            {label}
          </TooltipContent>
        </Tooltip>
      );
    }

    return content;
  };

  return (
    <aside
      className={cn(
        'relative flex h-screen flex-col border-r border-border bg-card/50 transition-all duration-300',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo */}
      <div className={cn('flex h-16 items-center border-b border-border px-4', collapsed && 'justify-center px-2')}>
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/30 bg-primary/10">
            <svg
              className="h-4 w-4 text-primary"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M6 9L12 5L18 9V15L12 19L6 15V9Z" />
              <circle cx="12" cy="12" r="3" fill="currentColor" />
            </svg>
          </div>
          {!collapsed && (
            <span className="font-display text-lg font-semibold text-gradient-cyan">
              empla
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        <div className="space-y-1">
          {navItems.map((item) => (
            <NavItem key={item.href} {...item} />
          ))}
        </div>

        <Separator className="my-4" />

        <div className="space-y-1">
          {!collapsed && (
            <span className="mb-2 block px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Quick Actions
            </span>
          )}
          {actionItems.map((item) => (
            <NavItem key={item.href} {...item} />
          ))}
        </div>
      </nav>

      {/* Settings */}
      <div className="border-t border-border p-3">
        <NavItem href="/settings" icon={Settings} label="Settings" disabled />
      </div>

      {/* Collapse toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute -right-3 top-20 z-10 h-6 w-6 rounded-full border border-border bg-card shadow-sm hover:bg-accent"
        onClick={onToggle}
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </Button>
    </aside>
  );
}
