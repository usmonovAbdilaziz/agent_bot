import designs from './designs.json';

export const DESIGNS = Object.fromEntries(designs.map(design => [design.id, design]));
