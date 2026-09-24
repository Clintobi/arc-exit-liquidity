// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ArcFlagRegistry
/// @notice On-chain record of observable facts about tokens traded on Arc.
///
/// Arc has ~200k Uniswap V4 pools and a handful of ways to lose money that are
/// knowable before you trade: a token whose symbol reads USDC while its address
/// is not USDC, a pool whose fee makes selling pointless, a pool only its own
/// deployer has ever touched. Those facts exist in chain history but nothing
/// surfaces them at the moment anyone would act on them.
///
/// This contract holds them where a wallet, aggregator or front end can read
/// them in one call, instead of each having to index the chain themselves.
///
/// Design notes:
///
/// - Every flag is a STATEMENT OF FACT, not a verdict. `SYMBOL_COLLISION` means
///   "this token reports a symbol that collides with a canonical asset and its
///   address differs" — not "this is a scam". Consumers decide what to do. The
///   supporting numbers are stored alongside so a reader can check the claim
///   rather than trust it.
/// - Flags are revisable and clearable. A detector that cannot be corrected is
///   a liability, and mislabelling someone's token is a real harm.
/// - Publishers are an allowlist, starting as one address. This is honest about
///   being centralised today; `setPublisher` is the seam for changing that.
contract ArcFlagRegistry {
    // ---------------------------------------------------------------- flags

    /// @dev Reports a symbol colliding with a canonical asset at a different address.
    uint8 public constant SYMBOL_COLLISION = 1 << 0;
    /// @dev Observed in a pool whose realised swap fee is at or above the threshold.
    uint8 public constant HIGH_FEE = 1 << 1;
    /// @dev Every swap in its pools came from a single sender.
    uint8 public constant SINGLE_TRADER = 1 << 2;
    /// @dev A pool exists but no swap has ever settled in it.
    uint8 public constant NEVER_TRADED = 1 << 3;
    /// @dev Fee is hook-controlled per swap, so no fixed rate can be quoted.
    uint8 public constant DYNAMIC_FEE = 1 << 4;

    /// @notice Fee threshold for HIGH_FEE, in hundredths of a bip (500000 = 50%).
    uint32 public constant HIGH_FEE_THRESHOLD = 500_000;

    // --------------------------------------------------------------- record

    /// @param flags       bitmask of the constants above
    /// @param pools       pools observed containing this token
    /// @param traders     distinct senders observed swapping it
    /// @param maxFee      highest REALISED fee seen, hundredths of a bip
    /// @param blockSeen   Arc block through which the assessment holds
    /// @param epoch       publication round, so consumers can spot stale rows
    struct Record {
        uint8 flags;
        uint32 pools;
        uint32 traders;
        uint32 maxFee;
        uint64 blockSeen;
        uint32 epoch;
    }

    mapping(address => Record) private _records;

    address[] private _flagged;
    mapping(address => bool) private _listed;

    // ---------------------------------------------------------------- admin

    address public owner;
    mapping(address => bool) public isPublisher;

    /// @notice Increments on each publishing round.
    uint32 public epoch;

    // --------------------------------------------------------------- events

    event FlagsSet(
        address indexed token,
        uint8 flags,
        uint32 pools,
        uint32 traders,
        uint32 maxFee,
        uint64 blockSeen,
        uint32 epoch
    );
    event FlagsCleared(address indexed token, uint32 epoch);
    event PublisherSet(address indexed publisher, bool allowed);
    event OwnerTransferred(address indexed from, address indexed to);
    event EpochOpened(uint32 indexed epoch, uint64 blockSeen);

    // --------------------------------------------------------------- errors

    error NotOwner();
    error NotPublisher();
    error LengthMismatch();
    error ZeroAddress();
    error EmptyFlags();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyPublisher() {
        if (!isPublisher[msg.sender]) revert NotPublisher();
        _;
    }

    constructor() {
        owner = msg.sender;
        isPublisher[msg.sender] = true;
        emit OwnerTransferred(address(0), msg.sender);
        emit PublisherSet(msg.sender, true);
    }

    // ----------------------------------------------------------- publishing

    /// @notice Opens a publishing round. Consumers can compare `epoch` on a
    /// record against the current one to tell how fresh an assessment is.
    function openEpoch(uint64 blockSeen) external onlyPublisher returns (uint32) {
        unchecked { epoch += 1; }
        emit EpochOpened(epoch, blockSeen);
        return epoch;
    }

    /// @notice Write one token's record.
    function setFlags(
        address token,
        uint8 flags,
        uint32 pools,
        uint32 traders,
        uint32 maxFee,
        uint64 blockSeen
    ) public onlyPublisher {
        if (token == address(0)) revert ZeroAddress();
        // A record with no flags is a clear, and has its own entry point so
        // that removal is always explicit rather than an accident of a 0 arg.
        if (flags == 0) revert EmptyFlags();

        if (!_listed[token]) {
            _listed[token] = true;
            _flagged.push(token);
        }
        _records[token] = Record({
            flags: flags,
            pools: pools,
            traders: traders,
            maxFee: maxFee,
            blockSeen: blockSeen,
            epoch: epoch
        });
        emit FlagsSet(token, flags, pools, traders, maxFee, blockSeen, epoch);
    }

    /// @notice Write many records in one transaction.
    /// @dev The detector produces hundreds of rows per round; one call each
    /// would make republishing cost more than it is worth.
    function setFlagsBatch(
        address[] calldata tokens,
        uint8[] calldata flags,
        uint32[] calldata pools,
        uint32[] calldata traders,
        uint32[] calldata maxFees,
        uint64 blockSeen
    ) external onlyPublisher {
        uint256 n = tokens.length;
        if (
            flags.length != n || pools.length != n ||
            traders.length != n || maxFees.length != n
        ) revert LengthMismatch();
        for (uint256 i; i < n; ) {
            setFlags(tokens[i], flags[i], pools[i], traders[i], maxFees[i], blockSeen);
            unchecked { ++i; }
        }
    }

    /// @notice Remove a token's record.
    /// @dev Deliberately public-facing and cheap. If this registry mislabels a
    /// token, correcting it must not be harder than publishing it.
    function clearFlags(address token) public onlyPublisher {
        delete _records[token];
        emit FlagsCleared(token, epoch);
    }

    function clearFlagsBatch(address[] calldata tokens) external onlyPublisher {
        for (uint256 i; i < tokens.length; ) {
            clearFlags(tokens[i]);
            unchecked { ++i; }
        }
    }

    // ------------------------------------------------------------- reading

    /// @notice Full record for a token. A zero `flags` means nothing is recorded.
    function getRecord(address token) external view returns (Record memory) {
        return _records[token];
    }

    /// @notice Bitmask only — the cheapest question a front end can ask.
    function flagsOf(address token) external view returns (uint8) {
        return _records[token].flags;
    }

    /// @notice True if `token` carries `flag`.
    function hasFlag(address token, uint8 flag) external view returns (bool) {
        return _records[token].flags & flag != 0;
    }

    /// @notice Any flag at all.
    function isFlagged(address token) external view returns (bool) {
        return _records[token].flags != 0;
    }

    /// @notice Batch read for a list view.
    function flagsOfBatch(address[] calldata tokens) external view returns (uint8[] memory out) {
        out = new uint8[](tokens.length);
        for (uint256 i; i < tokens.length; ) {
            out[i] = _records[tokens[i]].flags;
            unchecked { ++i; }
        }
    }

    /// @notice Count of tokens ever written. Includes entries later cleared,
    /// whose `flags` read zero — enumeration is for indexers, not for trusting.
    function flaggedCount() external view returns (uint256) {
        return _flagged.length;
    }

    /// @notice Page through written tokens.
    function flaggedAt(uint256 start, uint256 count) external view returns (address[] memory out) {
        uint256 end = start + count;
        if (end > _flagged.length) end = _flagged.length;
        if (start >= end) return new address[](0);
        out = new address[](end - start);
        for (uint256 i; i < out.length; ) {
            out[i] = _flagged[start + i];
            unchecked { ++i; }
        }
    }

    // --------------------------------------------------------------- admin

    function setPublisher(address publisher, bool allowed) external onlyOwner {
        if (publisher == address(0)) revert ZeroAddress();
        isPublisher[publisher] = allowed;
        emit PublisherSet(publisher, allowed);
    }

    function transferOwnership(address to) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        emit OwnerTransferred(owner, to);
        owner = to;
    }
}
