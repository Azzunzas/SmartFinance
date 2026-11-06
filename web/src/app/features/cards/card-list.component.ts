import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

import { AccountsService } from '../../core/api/generated/accounts/accounts.service';
import { BillsService } from '../../core/api/generated/bills/bills.service';
import type { BillOut } from '../../core/api/generated/smartFinanceAPI.schemas';

const PREVIOUS_BILLS_SHOWN = 3;

@Component({
  selector: 'app-card-list',
  imports: [CurrencyPipe, DatePipe],
  templateUrl: './card-list.component.html',
  styleUrl: './card-list.component.css'
})
export class CardListComponent {
  private readonly accountsService = inject(AccountsService);
  private readonly billsService = inject(BillsService);

  protected readonly cards = rxResource({
    stream: () => this.accountsService.listAllApiAccountsGet({ type: 'CREDIT' })
  });

  protected readonly bills = rxResource({
    stream: () => this.billsService.listAllApiBillsGet({ limit: 100 })
  });

  protected readonly creditCards = computed(
    () => this.cards.value() ?? []
  );

  // A API já devolve as faturas da mais recente para a mais antiga.
  private readonly billsByCard = computed(() => {
    const byCard = new Map<number, BillOut[]>();
    for (const bill of this.bills.value() ?? []) {
      byCard.set(bill.account_id, [...(byCard.get(bill.account_id) ?? []), bill]);
    }
    return byCard;
  });

  // `due_date` chega como 'YYYY-MM-DD'; comparar strings nesse formato é comparar datas.
  private readonly today = localIsoDate(new Date());

  protected readonly totalDue = computed(() =>
    this.creditCards().reduce((total, card) => {
      const bill = this.latestBill(card.id);
      return bill && this.isDue(bill) ? total + Math.max(Number(bill.total_amount), 0) : total;
    }, 0)
  );

  protected latestBill(cardId: number): BillOut | undefined {
    return this.billsByCard().get(cardId)?.[0];
  }

  protected previousBills(cardId: number): BillOut[] {
    return (this.billsByCard().get(cardId) ?? []).slice(1, 1 + PREVIOUS_BILLS_SHOWN);
  }

  protected isDue(bill: BillOut): boolean {
    return bill.due_date >= this.today;
  }

  protected utilizationPercent(balance: string | null, limit: string | null): number {
    const numericLimit = Number(limit);
    return numericLimit > 0 ? Math.min((Number(balance ?? 0) / numericLimit) * 100, 100) : 0;
  }
}

function localIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}
