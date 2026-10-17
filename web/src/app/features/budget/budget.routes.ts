import { Routes } from '@angular/router';

import { BudgetCreateComponent } from './budget-create.component';
import { BudgetDetailComponent } from './budget-detail.component';
import { BudgetListComponent } from './budget-list.component';

export const BUDGET_ROUTES: Routes = [
  { path: '', component: BudgetListComponent },
  { path: 'new', component: BudgetCreateComponent },
  { path: ':id', component: BudgetDetailComponent }
];
