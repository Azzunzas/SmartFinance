import { Pipe, PipeTransform } from '@angular/core';

import { PlannedKind } from '../../core/api/generated/smartFinanceAPI.schemas';

const LABELS: Record<PlannedKind, string> = {
  FIXED_EXPENSE: 'Despesa fixa',
  INCOME: 'Receita',
  VARIABLE_BUDGET: 'Orçamento variável'
};

@Pipe({ name: 'plannedKindLabel' })
export class PlannedKindLabelPipe implements PipeTransform {
  transform(value: string): string {
    return LABELS[value as PlannedKind] ?? value;
  }
}
