import { Pipe, PipeTransform } from '@angular/core';

import { Direction } from '../../core/api/generated/smartFinanceAPI.schemas';

const LABELS: Record<Direction, string> = {
  IN: 'Entrada',
  OUT: 'Saída'
};

@Pipe({ name: 'directionLabel' })
export class DirectionLabelPipe implements PipeTransform {
  transform(value: Direction): string {
    return LABELS[value];
  }
}
