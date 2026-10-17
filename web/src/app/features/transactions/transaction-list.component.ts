import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

import { AccountsService } from '../../core/api/generated/accounts/accounts.service';
import { CategoriesService } from '../../core/api/generated/categories/categories.service';
import {
  Direction,
  ListAllApiTransactionsGetParams,
  TransactionOut,
} from '../../core/api/generated/smartFinanceAPI.schemas';
import { TransactionsService } from '../../core/api/generated/transactions/transactions.service';
import { PaymentMethodLabelPipe } from '../../shared/pipes/payment-method-label.pipe';
import { TransactionBulkClassificationComponent } from './transaction-bulk-classification.component';
import { TransactionClassificationComponent } from './transaction-classification.component';

type TransactionFilters = Pick<
  ListAllApiTransactionsGetParams,
  'period' | 'direction' | 'account_id' | 'category_id' | 'payment_method' | 'search' | 'cursor'
>;

@Component({
  selector: 'app-transaction-list',
  imports: [
    CurrencyPipe,
    DatePipe,
    PaymentMethodLabelPipe,
    TransactionClassificationComponent,
    TransactionBulkClassificationComponent,
  ],
  templateUrl: './transaction-list.component.html',
  styleUrl: './transaction-list.component.css',
})
export class TransactionListComponent {
  private readonly transactionsService = inject(TransactionsService);
  private readonly accountsService = inject(AccountsService);
  private readonly categoriesService = inject(CategoriesService);

  protected readonly filters = signal<TransactionFilters>({ cursor: null });
  protected readonly previousCursors = signal<Array<string | null>>([]);
  protected readonly currentPage = computed(() => this.previousCursors().length + 1);
  protected readonly selectedTransaction = signal<TransactionOut | null>(null);
  protected readonly selectedIds = signal<ReadonlySet<number>>(new Set());
  protected readonly selectedIdList = computed(() => [...this.selectedIds()]);
  protected readonly bulkModalOpen = signal(false);
  protected readonly page = rxResource({
    params: () => this.filters(),
    stream: ({ params }) =>
      this.transactionsService.listAllApiTransactionsGet({ ...params, limit: 50 }),
  });
  protected readonly accounts = rxResource({
    stream: () => this.accountsService.listAllApiAccountsGet(),
  });
  protected readonly categories = rxResource({
    stream: () => this.categoriesService.listAllApiCategoriesGet(),
  });
  protected readonly allPageSelected = computed(() => {
    const items = this.page.value()?.items ?? [];
    return items.length > 0 && items.every((item) => this.selectedIds().has(item.id));
  });

  protected applySearch(search: string): void {
    this.replaceFilters({ search: search.trim() || null });
  }
  protected setPeriod(period: string): void {
    this.replaceFilters({ period: period || null });
  }
  protected setDirection(direction: string): void {
    this.replaceFilters({ direction: (direction || null) as Direction | null });
  }
  protected setAccount(accountId: string): void {
    this.replaceFilters({ account_id: accountId ? Number(accountId) : null });
  }
  protected setCategory(categoryId: string): void {
    this.replaceFilters({ category_id: categoryId ? Number(categoryId) : null });
  }
  protected setPaymentMethod(paymentMethod: string): void {
    this.replaceFilters({ payment_method: paymentMethod || null });
  }
  protected clearFilters(): void {
    this.filters.set({ cursor: null });
    this.previousCursors.set([]);
    this.clearSelection();
  }

  protected nextPage(): void {
    const nextCursor = this.page.value()?.next_cursor;
    if (!nextCursor) return;
    this.previousCursors.update((history) => [...history, this.filters().cursor ?? null]);
    this.filters.update((filters) => ({ ...filters, cursor: nextCursor }));
    this.clearSelection();
  }

  protected previousPage(): void {
    const history = this.previousCursors();
    if (!history.length) return;
    const cursor = history.at(-1) ?? null;
    this.previousCursors.set(history.slice(0, -1));
    this.filters.update((filters) => ({ ...filters, cursor }));
    this.clearSelection();
  }

  protected amountClass(direction: Direction): 'positive' | 'negative' {
    return direction === 'IN' ? 'positive' : 'negative';
  }

  protected hasManualOverride(transaction: TransactionOut): boolean {
    return (
      transaction.category_id_manual !== null ||
      transaction.is_internal_transfer_manual !== null ||
      transaction.is_card_payment_manual !== null
    );
  }

  protected classificationSaved(): void {
    this.selectedTransaction.set(null);
    this.page.reload();
  }

  protected toggleTransaction(transactionId: number, checked: boolean): void {
    this.selectedIds.update((current) => {
      const next = new Set(current);
      if (checked) next.add(transactionId);
      else next.delete(transactionId);
      return next;
    });
  }

  protected togglePage(checked: boolean): void {
    this.selectedIds.set(
      checked ? new Set((this.page.value()?.items ?? []).map((item) => item.id)) : new Set(),
    );
  }

  protected bulkClassificationSaved(): void {
    this.bulkModalOpen.set(false);
    this.clearSelection();
    this.page.reload();
  }

  protected clearSelection(): void {
    this.selectedIds.set(new Set());
  }

  private replaceFilters(patch: Omit<TransactionFilters, 'cursor'>): void {
    this.filters.update((filters) => ({ ...filters, ...patch, cursor: null }));
    this.previousCursors.set([]);
    this.clearSelection();
  }
}
