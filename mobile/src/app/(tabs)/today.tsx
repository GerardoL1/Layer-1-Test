import { Page, PageState } from '../../components/Page';
import { Text } from '../../components/Text';
import { useApi, useLoad } from '../../api/useApi';
import { useTheme } from '../../theme/theme';

// Temporary page for step 4a: proves the app reaches the server. Step 4c builds the real Today.
export default function TodayScreen() {
  const api = useApi();
  const { statusColor } = useTheme();
  const { data, error, loading } = useLoad(() => api.today(), api);
  return (
    <Page>
      <Text variant="labelMedium" color="textSecondary">Today</Text>
      <PageState loading={loading} error={error} />
      {data && (
        <>
          <Text variant="labelMedium" style={{ marginTop: 24, color: statusColor(data.readiness?.status) }}>
            Readiness · {data.readiness?.status ?? 'none'}
          </Text>
          <Text variant="scoreHero">{data.readiness?.score ?? '–'}</Text>
          <Text variant="body" color="textSecondary">Night of {data.night_date ?? 'none yet'}</Text>
        </>
      )}
    </Page>
  );
}
