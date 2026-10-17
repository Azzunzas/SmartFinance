import { Component, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import {
  BulkClassifyRequest,
  BulkClassifyRequestResetFieldsItem,
  CategoryOut,
} from '../../core/api/generated/smartFinanceAPI.schemas';
import { TransactionsService } from '../../core/api/generated/transactions/transactions.service';
import { ModalDirective } from '../../shared/modal/modal.directive';

type BooleanChoice = 'unchanged' | 'automatic' | 'true' | 'false';

@Component({
  selector: 'app-transaction-bulk-classification',
  imports: [ModalDirective, ReactiveFormsModule],
  templateUrl: './transaction-bulk-classification.component.html',
  styleUrls: [
    './transaction-classification.component.css',
    './transaction-bulk-classification.component.css',
  ],
})
export class TransactionBulkClassificationComponent {
  private readonly fb = inject(FormBuilder);
  private readonly transactionsService = inject(TransactionsService);

  readonly transactionIds = input.required<number[]>();
  readonly categories = input.required<CategoryOut[]>();
  readonly cancelled = output<void>();
  readonly saved = output<void>();
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);

  protected readonly form = this.fb.group({
    category: this.fb.control('unchanged', { nonNullable: true }),
    is_internal_transfer: this.fb.control<BooleanChoice>('unchanged', { nonNullable: true }),
    is_card_payment: this.fb.control<BooleanChoice>('unchanged', { nonNullable: true }),
    exclude_from_analysis: this.fb.control<BooleanChoice>('unchanged', { nonNullable: true }),
    change_note: this.fb.control(false, { nonNullable: true }),
    note: this.fb.control('', { nonNullable: true }),
  });

  protected submit(): void {
    const value = this.form.getRawValue();
    const request: BulkClassifyRequest = { transaction_ids: this.transactionIds() };
    const resetFields: BulkClassifyRequestResetFieldsItem[] = [];

    if (value.category === 'automatic') resetFields.push('category_id');
    else if (value.category === 'none') request.category_id = null;
    else if (value.category !== 'unchanged') request.category_id = Number(value.category);

    this.applyBoolean(request, 'is_internal_transfer', value.is_internal_transfer, resetFields);
    this.applyBoolean(request, 'is_card_payment', value.is_card_payment, resetFields);
    this.applyBoolean(request, 'exclude_from_analysis', value.exclude_from_analysis);
    if (value.change_note) request.note = value.note.trim() || null;
    if (resetFields.length > 0) request.reset_fields = resetFields;

    if (Object.keys(request).length === 1) {
      this.errorMessage.set('Escolha pelo menos uma alteração para aplicar.');
      return;
    }

    this.saving.set(true);
    this.errorMessage.set(null);
    this.transactionsService.bulkClassifyApiTransactionsBulkClassifyPost(request).subscribe({
      next: (result) => {
        if (result.missing_ids.length > 0) {
          this.saving.set(false);
          this.errorMessage.set(
            `${result.missing_ids.length} transação(ões) não foi(ram) encontrada(s).`,
          );
          return;
        }
        this.saved.emit();
      },
      error: () => {
        this.saving.set(false);
        this.errorMessage.set('Não foi possível aplicar a classificação em lote.');
      },
    });
  }

  private applyBoolean(
    request: BulkClassifyRequest,
    field: 'is_internal_transfer' | 'is_card_payment' | 'exclude_from_analysis',
    choice: BooleanChoice,
    resetFields?: BulkClassifyRequestResetFieldsItem[],
  ): void {
    if (choice === 'automatic' && resetFields && field !== 'exclude_from_analysis') {
      resetFields.push(field);
    } else if (choice !== 'unchanged') {
      request[field] = choice === 'true';
    }
  }
}
