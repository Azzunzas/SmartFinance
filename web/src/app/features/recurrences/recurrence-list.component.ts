import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { RecurrencesService } from '../../core/api/generated/recurrences/recurrences.service';

@Component({
  selector: 'app-recurrence-list',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, RouterLink],
  templateUrl: './recurrence-list.component.html',
  styleUrl: './recurrence-list.component.css'
})
export class RecurrenceListComponent {
  private readonly recurrencesService = inject(RecurrencesService);

  protected readonly candidates = rxResource({
    stream: () => this.recurrencesService.listCandidatesApiRecurrencesGet()
  });

  protected readonly incomeCandidates = computed(
    () => this.candidates.value()?.filter((candidate) => candidate.direction === 'IN') ?? []
  );

  protected readonly expenseCandidates = computed(
    () => this.candidates.value()?.filter((candidate) => candidate.direction === 'OUT') ?? []
  );

  protected readonly recurringIncome = computed(() =>
    this.incomeCandidates().reduce((total, candidate) => total + Number(candidate.avg_amount), 0)
  );

  protected readonly recurringExpenses = computed(() =>
    this.expenseCandidates().reduce((total, candidate) => total + Number(candidate.avg_amount), 0)
  );

  protected readonly recurringBalance = computed(
    () => this.recurringIncome() - this.recurringExpenses()
  );
}
