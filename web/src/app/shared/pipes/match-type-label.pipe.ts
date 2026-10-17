import { Pipe, PipeTransform } from '@angular/core';

import { MatchType } from '../../core/api/generated/smartFinanceAPI.schemas';

const LABELS: Record<MatchType, string> = {
  CONTAINS: 'Contém',
  REGEX: 'Expressão regular',
  MERCHANT: 'Estabelecimento',
  AMOUNT_RANGE: 'Faixa de valor'
};

@Pipe({ name: 'matchTypeLabel' })
export class MatchTypeLabelPipe implements PipeTransform {
  transform(value: MatchType): string {
    return LABELS[value];
  }
}
