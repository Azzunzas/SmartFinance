import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

import { AccountsService } from '../../core/api/generated/accounts/accounts.service';

@Component({
  selector: 'app-card-list',
  imports: [CurrencyPipe, DatePipe],
  templateUrl: './card-list.component.html',
  styleUrl: './card-list.component.css'
})
export class CardListComponent {
  private readonly accountsService = inject(AccountsService);

  protected readonly cards = rxResource({
    stream: () => this.accountsService.listAllApiAccountsGet({ type: 'CREDIT' })
  });

  protected readonly creditCards = computed(
    () => this.cards.value() ?? []
  );

  protected readonly totalBill = computed(() =>
    this.creditCards().reduce((total, card) => total + Number(card.balance ?? 0), 0)
  );

  protected utilizationPercent(balance: string | null, limit: string | null): number {
    const numericLimit = Number(limit);
    return numericLimit > 0 ? Math.min((Number(balance ?? 0) / numericLimit) * 100, 100) : 0;
  }
}
