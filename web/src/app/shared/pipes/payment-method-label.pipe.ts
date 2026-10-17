import { Pipe, PipeTransform } from '@angular/core';

const LABELS: Record<string, string> = { PIX: 'PIX', TED: 'TED', DOC: 'DOC', BOLETO: 'Boleto' };

@Pipe({ name: 'paymentMethodLabel' })
export class PaymentMethodLabelPipe implements PipeTransform {
  transform(value: string | null): string {
    return value ? (LABELS[value] ?? value) : 'Não informado';
  }
}
