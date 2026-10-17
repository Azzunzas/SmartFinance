import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';

import { AccountsService } from '../../core/api/generated/accounts/accounts.service';

@Component({
  selector: 'app-account-list',
  imports: [CurrencyPipe, DatePipe],
  templateUrl: './account-list.component.html',
  styleUrl: './account-list.component.css'
})
export class AccountListComponent {
  private readonly accountsService = inject(AccountsService);

  protected readonly accounts = rxResource({
    stream: () => this.accountsService.listAllApiAccountsGet({ type: 'BANK' })
  });

  protected readonly bankAccounts = computed(
    () => this.accounts.value() ?? []
  );

  protected readonly totalBalance = computed(() =>
    this.bankAccounts().reduce((total, account) => total + Number(account.balance), 0)
  );

  protected amountClass(value: string | null): 'positive' | 'negative' {
    return Number(value) >= 0 ? 'positive' : 'negative';
  }
}
