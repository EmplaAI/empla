import { useLocation } from 'react-router-dom';
import { UserMenu } from './user-menu';

const pageTitles: Record<string, { title: string; description: string }> = {
  '/': {
    title: 'Command Center',
    description: 'Overview of your digital workforce',
  },
  '/employees': {
    title: 'Employees',
    description: 'Manage your digital employees',
  },
  '/employees/new': {
    title: 'New Employee',
    description: 'Create a new digital employee',
  },
  '/activity': {
    title: 'Activity',
    description: 'Recent activity across all employees',
  },
  '/settings': {
    title: 'Settings',
    description: 'Configure your dashboard',
  },
};

function getPageInfo(pathname: string) {
  // Check for exact match first
  if (pageTitles[pathname]) {
    return pageTitles[pathname];
  }

  // Check for employee detail page
  if (pathname.match(/^\/employees\/[^/]+$/)) {
    return {
      title: 'Employee Details',
      description: 'View and manage employee',
    };
  }

  return {
    title: 'Dashboard',
    description: '',
  };
}

export function Header() {
  const location = useLocation();
  const { title, description } = getPageInfo(location.pathname);

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur-sm">
      <div className="flex flex-col">
        <h1 className="font-display text-lg font-semibold tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Status indicator */}
        <div className="flex items-center gap-2 rounded-full border border-status-active/30 bg-status-active/10 px-3 py-1">
          <div className="h-2 w-2 rounded-full bg-status-active animate-pulse" />
          <span className="font-mono text-xs text-status-active">SYSTEM ONLINE</span>
        </div>

        <UserMenu />
      </div>
    </header>
  );
}
