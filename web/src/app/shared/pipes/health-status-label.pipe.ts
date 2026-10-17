import { Pipe, PipeTransform } from '@angular/core';

import { HealthStatus } from '../../core/api/generated/smartFinanceAPI.schemas';

const LABELS: Record<HealthStatus, string> = {
  HEALTHY: 'Saudável',
  ATTENTION: 'Atenção',
  CRITICAL: 'Crítica',
};

@Pipe({ name: 'healthStatusLabel' })
export class HealthStatusLabelPipe implements PipeTransform {
  transform(value: HealthStatus): string {
    return LABELS[value];
  }
}
