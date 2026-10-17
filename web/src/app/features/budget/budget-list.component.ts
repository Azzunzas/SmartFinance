import { CurrencyPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { PlannedVsActualOut } from '../../core/api/generated/smartFinanceAPI.schemas';
import { MetricsService } from '../../core/api/generated/metrics/metrics.service';
import { PlannedKindLabelPipe } from '../../shared/pipes/planned-kind-label.pipe';
import { ModalDirective } from '../../shared/modal/modal.directive';
import { BudgetCreateComponent } from './budget-create.component';

const CURRENT_PERIOD = new Date().toISOString().slice(0, 7);

@Component({
  selector: 'app-budget-list',
  imports: [BudgetCreateComponent, CurrencyPipe, ModalDirective, RouterLink, PlannedKindLabelPipe],
  templateUrl: './budget-list.component.html',
  styleUrl: './budget-list.component.css',
})
export class BudgetListComponent {
  private readonly metricsService = inject(MetricsService);

  protected readonly period = signal(CURRENT_PERIOD);
  protected readonly budget = rxResource({
    stream: () =>
      this.metricsService.plannedVsActualApiMetricsPlannedVsActualGet({ period: this.period() }),
  });
  protected readonly addModalOpen = signal(false);

  protected readonly incomeItems = computed(
    () => this.budget.value()?.filter((item) => item.kind === 'INCOME') ?? [],
  );

  protected readonly expenseItems = computed(
    () => this.budget.value()?.filter((item) => item.kind !== 'INCOME') ?? [],
  );

  protected readonly expectedIncome = computed(() =>
    this.incomeItems().reduce((sum, item) => sum + Number(item.expected_amount), 0),
  );

  protected readonly plannedExpenses = computed(() =>
    this.expenseItems().reduce((sum, item) => sum + Number(item.expected_amount), 0),
  );

  protected readonly actualIncome = computed(() =>
    this.incomeItems().reduce((sum, item) => sum + Number(item.matched_amount), 0),
  );

  protected readonly actualExpenses = computed(() =>
    this.expenseItems().reduce((sum, item) => sum + Number(item.matched_amount), 0),
  );

  protected readonly available = computed(() => this.expectedIncome() - this.plannedExpenses());

  protected closeAddModal(): void {
    this.addModalOpen.set(false);
  }

  protected setPeriod(period: string): void {
    if (period) this.period.set(period);
  }

  protected onItemCreated(): void {
    this.closeAddModal();
    this.budget.reload();
  }

  protected progressPercent(item: PlannedVsActualOut): number {
    const expected = Number(item.expected_amount);
    return expected > 0 ? Math.min((Number(item.matched_amount) / expected) * 100, 100) : 0;
  }

  protected progressLabel(item: PlannedVsActualOut): string {
    const expected = Number(item.expected_amount);
    const actual = Number(item.matched_amount);
    const tolerance = expected * (Number(item.tolerance_pct) / 100);

    if (actual === 0) return 'Sem lançamento no período';
    if (item.kind === 'INCOME') {
      return actual + tolerance < expected ? 'Abaixo do esperado' : 'Dentro do esperado';
    }
    return actual > expected + tolerance ? 'Acima do orçamento' : 'Dentro do orçamento';
  }

  protected progressStatus(
    item: PlannedVsActualOut,
  ): 'progress-ok' | 'progress-warning' | 'progress-over' {
    const expected = Number(item.expected_amount);
    const actual = Number(item.matched_amount);
    const tolerance = expected * (Number(item.tolerance_pct) / 100);

    if (item.kind === 'INCOME') {
      return actual + tolerance < expected ? 'progress-warning' : 'progress-ok';
    }
    return actual > expected + tolerance ? 'progress-over' : 'progress-ok';
  }
}
