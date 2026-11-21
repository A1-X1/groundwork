import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(__dirname, '../../..');
const schema = JSON.parse(
  readFileSync(resolve(root, 'shared/contracts/score_response.schema.json'), 'utf8'),
);

function validator() {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  return ajv.compile(schema);
}

describe('score_response contract', () => {
  it('accepts the frontend fixture', () => {
    const fixture = JSON.parse(
      readFileSync(resolve(__dirname, '../fixtures/score_response.json'), 'utf8'),
    );
    const validate = validator();
    expect(validate(fixture), JSON.stringify(validate.errors)).toBe(true);
    expect(fixture.cells.length).toBeGreaterThan(1000);
  });

  it('accepts the shared example', () => {
    const example = JSON.parse(
      readFileSync(resolve(root, 'shared/contracts/score_response.example.json'), 'utf8'),
    );
    expect(validator()(example)).toBe(true);
  });

  it('rejects a masked cell typed wrongly', () => {
    const bad = {
      profile: 'x',
      resolution: 8,
      generated_at: '2026-11-21T10:00:00Z',
      cells: [{ h3: '88195da49bfffff', score: 'high', masked: false, breakdown: {} }],
    };
    expect(validator()(bad)).toBe(false);
  });
});
