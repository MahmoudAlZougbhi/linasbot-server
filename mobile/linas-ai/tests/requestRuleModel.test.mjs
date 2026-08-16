/**
 * Request rule helpers — type, collects footer, published graph status.
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/requestRuleModel.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  collectsPhrase,
  createRequestRule,
  destinationFromType,
  isGraphPublished,
  matchesRequestQuery,
  parseGraphRow,
  parseRequestRule,
  ruleToRecord,
} from '../src/features/cm/requestRules/requestRuleModel.ts';

test('parseRequestRule defaults type and search', () => {
  const item = parseRequestRule({ id: 'r1', name: 'Laser appointment', notes: 'Collect name and phone' });
  assert.equal(item.type, 'APPOINTMENT');
  assert.equal(destinationFromType(item.type), 'appointment');
  assert.equal(matchesRequestQuery(item, 'laser'), true);
  assert.equal(matchesRequestQuery(item, 'order'), false);
  assert.equal(ruleToRecord(createRequestRule('r2')).enabled, true);
});

test('collects footer and published status come from graph payload', () => {
  const graph = parseGraphRow({
    definition_id: 'def1',
    source_item_id: 'r1',
    status: 'active',
    required_information: [
      { key: 'name', label: 'name' },
      { key: 'phone', label: 'phone' },
      { key: 'branch', label: 'branch' },
      { key: 'time', label: 'preferred time' },
    ],
  });
  assert.equal(isGraphPublished(graph), true);
  assert.equal(collectsPhrase(graph, 'none'), 'name, phone, branch and preferred time');
  assert.equal(isGraphPublished(parseGraphRow({ status: 'draft' })), false);
  assert.equal(collectsPhrase(undefined, 'none'), 'none');
});
