// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ArcFlagRegistry} from "../src/ArcFlagRegistry.sol";

contract ArcFlagRegistryTest is Test {
    ArcFlagRegistry reg;

    address owner = address(this);
    address publisher = address(0xB0B);
    address stranger = address(0xBAD);

    // A real impostor found on Arc: reports the USDC symbol, is not USDC.
    address constant FAKE_USDC = 0x8E98a62a0000000000000000000000000000A8F9;
    address constant CLEAN = 0x00000000000000000000000000000000DeaDBeef;

    // Cached because a cheatcode applies to the NEXT external call, and an
    // inline FEE argument IS one — it would swallow the prank or
    // the expectRevert before setFlags ever runs.
    uint8 SYMBOL; uint8 FEE; uint8 SOLO; uint8 DEAD;

    function setUp() public {
        reg = new ArcFlagRegistry();
        SYMBOL = reg.SYMBOL_COLLISION();
        FEE = reg.HIGH_FEE();
        SOLO = reg.SINGLE_TRADER();
        DEAD = reg.NEVER_TRADED();
    }

    function test_deployerOwnsAndPublishes() public view {
        assertEq(reg.owner(), owner);
        assertTrue(reg.isPublisher(owner));
        assertEq(reg.epoch(), 0);
    }

    function test_setAndReadFlags() public {
        reg.setFlags(FAKE_USDC, SYMBOL, 7, 181, 10_000, 22_357_859);

        assertTrue(reg.isFlagged(FAKE_USDC));
        assertTrue(reg.hasFlag(FAKE_USDC, SYMBOL));
        assertFalse(reg.hasFlag(FAKE_USDC, FEE));

        ArcFlagRegistry.Record memory r = reg.getRecord(FAKE_USDC);
        assertEq(r.pools, 7);
        assertEq(r.traders, 181);
        assertEq(r.maxFee, 10_000);
        assertEq(r.blockSeen, 22_357_859);
    }

    function test_unwrittenTokenIsClean() public view {
        assertFalse(reg.isFlagged(CLEAN));
        assertEq(reg.flagsOf(CLEAN), 0);
    }

    function test_flagsCombine() public {
        uint8 both = SYMBOL | FEE;
        reg.setFlags(FAKE_USDC, both, 1, 4, 900_000, 1);
        assertTrue(reg.hasFlag(FAKE_USDC, SYMBOL));
        assertTrue(reg.hasFlag(FAKE_USDC, FEE));
        assertFalse(reg.hasFlag(FAKE_USDC, SOLO));
    }

    /// A registry that cannot be corrected is a liability, so clearing has to work.
    function test_clearRemovesTheRecord() public {
        reg.setFlags(FAKE_USDC, FEE, 1, 1, 900_000, 1);
        assertTrue(reg.isFlagged(FAKE_USDC));
        reg.clearFlags(FAKE_USDC);
        assertFalse(reg.isFlagged(FAKE_USDC));
        assertEq(reg.getRecord(FAKE_USDC).maxFee, 0);
    }

    /// Clearing must not be expressible as "set zero flags" by accident.
    function test_zeroFlagsReverts() public {
        vm.expectRevert(ArcFlagRegistry.EmptyFlags.selector);
        reg.setFlags(FAKE_USDC, 0, 1, 1, 0, 1);
    }

    function test_zeroAddressReverts() public {
        vm.expectRevert(ArcFlagRegistry.ZeroAddress.selector);
        reg.setFlags(address(0), FEE, 1, 1, 0, 1);
    }

    function test_batchWrite() public {
        address[] memory t = new address[](3);
        uint8[] memory f = new uint8[](3);
        uint32[] memory p = new uint32[](3);
        uint32[] memory tr = new uint32[](3);
        uint32[] memory mf = new uint32[](3);
        for (uint160 i; i < 3; ++i) {
            t[i] = address(uint160(0x1000) + i);
            f[i] = SYMBOL;
            p[i] = 2; tr[i] = 9; mf[i] = 10_000;
        }
        reg.setFlagsBatch(t, f, p, tr, mf, 22_357_859);

        uint8[] memory got = reg.flagsOfBatch(t);
        for (uint256 i; i < 3; ++i) assertEq(got[i], SYMBOL);
        assertEq(reg.flaggedCount(), 3);
    }

    function test_batchLengthMismatchReverts() public {
        address[] memory t = new address[](2);
        uint8[] memory f = new uint8[](1);
        uint32[] memory p = new uint32[](2);
        uint32[] memory tr = new uint32[](2);
        uint32[] memory mf = new uint32[](2);
        vm.expectRevert(ArcFlagRegistry.LengthMismatch.selector);
        reg.setFlagsBatch(t, f, p, tr, mf, 1);
    }

    function test_onlyPublisherCanWrite() public {
        vm.prank(stranger);
        vm.expectRevert(ArcFlagRegistry.NotPublisher.selector);
        reg.setFlags(FAKE_USDC, FEE, 1, 1, 0, 1);
    }

    function test_publisherCanBeGrantedAndRevoked() public {
        reg.setPublisher(publisher, true);
        vm.prank(publisher);
        reg.setFlags(FAKE_USDC, FEE, 1, 1, 900_000, 1);
        assertTrue(reg.isFlagged(FAKE_USDC));

        reg.setPublisher(publisher, false);
        vm.prank(publisher);
        vm.expectRevert(ArcFlagRegistry.NotPublisher.selector);
        reg.setFlags(CLEAN, FEE, 1, 1, 0, 1);
    }

    function test_onlyOwnerAdmin() public {
        vm.prank(stranger);
        vm.expectRevert(ArcFlagRegistry.NotOwner.selector);
        reg.setPublisher(stranger, true);
    }

    function test_epochAdvancesAndStamps() public {
        reg.openEpoch(22_357_859);
        assertEq(reg.epoch(), 1);
        reg.setFlags(FAKE_USDC, FEE, 1, 1, 900_000, 22_357_859);
        assertEq(reg.getRecord(FAKE_USDC).epoch, 1);

        reg.openEpoch(22_400_000);
        assertEq(reg.epoch(), 2);
        // The stale row keeps its old epoch, which is how a consumer spots it.
        assertEq(reg.getRecord(FAKE_USDC).epoch, 1);
    }

    function test_pagination() public {
        address[] memory t = new address[](5);
        uint8[] memory f = new uint8[](5);
        uint32[] memory p = new uint32[](5);
        uint32[] memory tr = new uint32[](5);
        uint32[] memory mf = new uint32[](5);
        for (uint160 i; i < 5; ++i) {
            t[i] = address(uint160(0x2000) + i);
            f[i] = DEAD;
        }
        reg.setFlagsBatch(t, f, p, tr, mf, 1);

        assertEq(reg.flaggedAt(0, 2).length, 2);
        assertEq(reg.flaggedAt(3, 10).length, 2);   // clamps at the end
        assertEq(reg.flaggedAt(9, 1).length, 0);    // past the end is empty
        assertEq(reg.flaggedAt(0, 5)[4], t[4]);
    }

    /// Rewriting must update in place, not append a duplicate.
    function test_rewriteDoesNotDuplicate() public {
        reg.setFlags(FAKE_USDC, FEE, 1, 1, 900_000, 1);
        reg.setFlags(FAKE_USDC, SYMBOL, 9, 2, 10_000, 2);
        assertEq(reg.flaggedCount(), 1);
        assertEq(reg.getRecord(FAKE_USDC).pools, 9);
        assertFalse(reg.hasFlag(FAKE_USDC, FEE));
    }

    function testFuzz_roundTrip(uint8 flags, uint32 pools, uint32 traders, uint32 maxFee) public {
        vm.assume(flags != 0);
        reg.setFlags(FAKE_USDC, flags, pools, traders, maxFee, 1);
        ArcFlagRegistry.Record memory r = reg.getRecord(FAKE_USDC);
        assertEq(r.flags, flags);
        assertEq(r.pools, pools);
        assertEq(r.traders, traders);
        assertEq(r.maxFee, maxFee);
    }
}
