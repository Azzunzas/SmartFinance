import { HealthStatusLabelPipe } from './health-status-label.pipe';

describe('HealthStatusLabelPipe', () => {
  const pipe = new HealthStatusLabelPipe();

  it.each([
    ['HEALTHY', 'Saudável'],
    ['ATTENTION', 'Atenção'],
    ['CRITICAL', 'Crítica'],
  ] as const)('translates %s to %s', (status, label) => {
    expect(pipe.transform(status)).toBe(label);
  });
});
