import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

export function IntegrationsCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const success = searchParams.get('success');
    const error = searchParams.get('error');
    const provider = searchParams.get('provider');

    if (success === 'true') {
      toast.success(
        provider
          ? `Successfully connected ${provider.replace(/_/g, ' ')}`
          : 'Successfully connected'
      );
    } else if (error) {
      const messages: Record<string, string> = {
        oauth_denied: 'OAuth authorization was denied.',
        invalid_state: 'OAuth session expired. Please try again.',
        token_exchange: 'Failed to exchange authorization code. Please try again.',
        missing_code: 'Authorization code was missing from the provider response.',
        config_missing: 'OAuth is not fully configured. Please contact your administrator.',
        internal: 'An internal error occurred. Please try again or contact support.',
        unknown: 'An unexpected error occurred.',
      };
      toast.error(messages[error] ?? `Connection failed: ${error}`);
    }

    navigate('/integrations', { replace: true });
  }, [searchParams, navigate]);

  return (
    <div className="flex h-64 items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}
