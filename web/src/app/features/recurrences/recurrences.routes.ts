import { Routes } from '@angular/router';

import { RecurrenceListComponent } from './recurrence-list.component';
import { RecurrencePromoteComponent } from './recurrence-promote.component';

export const RECURRENCES_ROUTES: Routes = [
  { path: '', component: RecurrenceListComponent },
  { path: ':id/promote', component: RecurrencePromoteComponent }
];
