import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProviders } from '@/providers/app-providers';
import { AuthGuard } from '@/components/auth/auth-guard';
import { ErrorBoundary } from '@/components/error-boundary';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { LoginPage } from '@/routes/login';
import { DashboardPage } from '@/routes/dashboard';
import { EmployeesPage } from '@/routes/employees';
import { EmployeeDetailPage } from '@/routes/employee-detail';
import { EmployeeNewPage } from '@/routes/employee-new';

export function App() {
  return (
    <BrowserRouter>
      <AppProviders>
        <ErrorBoundary>
          <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />

          {/* Protected routes */}
          <Route
            element={
              <AuthGuard>
                <DashboardLayout />
              </AuthGuard>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="employees" element={<EmployeesPage />} />
            <Route path="employees/new" element={<EmployeeNewPage />} />
            <Route path="employees/:id" element={<EmployeeDetailPage />} />
          </Route>

          {/* Catch all - redirect to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ErrorBoundary>
      </AppProviders>
    </BrowserRouter>
  );
}
