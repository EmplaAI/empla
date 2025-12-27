import { Link } from 'react-router-dom';
import { Plus, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const actions = [
  {
    label: 'New Employee',
    description: 'Create a digital worker',
    href: '/employees/new',
    icon: Plus,
    primary: true,
  },
  {
    label: 'View All',
    description: 'Manage employees',
    href: '/employees',
    icon: Users,
    primary: false,
  },
];

export function QuickActions() {
  return (
    <Card className="border-border/50 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-display">Quick Actions</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2">
        {actions.map((action) => (
          <Button
            key={action.href}
            variant={action.primary ? 'default' : 'outline'}
            className="justify-start gap-3 h-auto py-3"
            asChild
          >
            <Link to={action.href}>
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-background/50">
                <action.icon className="h-4 w-4" />
              </div>
              <div className="flex flex-col items-start text-left">
                <span className="font-medium">{action.label}</span>
                <span className="text-xs text-muted-foreground font-normal">
                  {action.description}
                </span>
              </div>
            </Link>
          </Button>
        ))}
      </CardContent>
    </Card>
  );
}
