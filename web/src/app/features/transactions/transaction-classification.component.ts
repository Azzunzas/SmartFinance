import { Component, effect, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import {
  CategoryOut,
  TransactionClassificationUpdate,
  TransactionClassificationUpdateResetFieldsItem,
  TransactionOut,
} from '../../core/api/generated/smartFinanceAPI.schemas';
import { TransactionsService } from '../../core/api/generated/transactions/transactions.service';
import { ModalDirective } from '../../shared/modal/modal.directive';

@Component({
  selector: 'app-transaction-classification',
  imports: [ModalDirective, ReactiveFormsModule],
  templateUrl: './transaction-classification.component.html',
  styleUrl: './transaction-classification.component.css',
})
export class TransactionClassificationComponent {
  private readonly fb = inject(FormBuilder);
  private readonly transactionsService = inject(TransactionsService);

  readonly transaction = input.required<TransactionOut>();
  readonly categories = input.required<CategoryOut[]>();
  readonly cancelled = output<void>();
  readonly saved = output<void>();
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);

  protected readonly form = this.fb.group({
    category_id: this.fb.control<number | null>(null),
    is_internal_transfer: this.fb.control(false, { nonNullable: true }),
    is_card_payment: this.fb.control(false, { nonNullable: true }),
    exclude_from_analysis: this.fb.control(false, { nonNullable: true }),
    note: this.fb.control('', { nonNullable: true }),
  });

  constructor() {
    effect(() => {
      const transaction = this.transaction();
      this.form.reset({
        category_id: transaction.category_id,
        is_internal_transfer: transaction.is_internal_transfer,
        is_card_payment: transaction.is_card_payment,
        exclude_from_analysis: transaction.exclude_from_analysis,
        note: transaction.note ?? '',
      });
    });
  }

  protected categoryName(categoryId: number | null): string {
    if (categoryId === null) return 'Sem categoria';
    return this.categories().find((category) => category.id === categoryId)?.name ?? 'Desconhecida';
  }

  protected booleanLabel(value: boolean): string {
    return value ? 'Sim' : 'Não';
  }

  protected resetOverride(field: TransactionClassificationUpdateResetFieldsItem): void {
    this.saving.set(true);
    this.errorMessage.set(null);
    this.transactionsService
      .patchClassificationApiTransactionsTransactionIdClassificationPatch(this.transaction().id, {
        reset_fields: [field],
      })
      .subscribe({
        next: () => this.saved.emit(),
        error: () => {
          this.saving.set(false);
          this.errorMessage.set('Não foi possível voltar à classificação automática.');
        },
      });
  }

  protected submit(): void {
    const transaction = this.transaction();
    const value = this.form.getRawValue();
    const patch: TransactionClassificationUpdate = {};

    if (value.category_id !== transaction.category_id) patch.category_id = value.category_id;
    if (value.is_internal_transfer !== transaction.is_internal_transfer) {
      patch.is_internal_transfer = value.is_internal_transfer;
    }
    if (value.is_card_payment !== transaction.is_card_payment) {
      patch.is_card_payment = value.is_card_payment;
    }
    if (value.exclude_from_analysis !== transaction.exclude_from_analysis) {
      patch.exclude_from_analysis = value.exclude_from_analysis;
    }
    const note = value.note.trim() || null;
    if (note !== transaction.note) patch.note = note;

    if (Object.keys(patch).length === 0) {
      this.cancelled.emit();
      return;
    }

    this.saving.set(true);
    this.errorMessage.set(null);
    this.transactionsService
      .patchClassificationApiTransactionsTransactionIdClassificationPatch(transaction.id, patch)
      .subscribe({
        next: () => this.saved.emit(),
        error: () => {
          this.saving.set(false);
          this.errorMessage.set('Não foi possível salvar a classificação.');
        },
      });
  }
}
